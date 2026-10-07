from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.auth.services import register_instructor
from app.extensions import db
from app.models import HelpSession, QueueEntry, StudentIdentity
from app.services import queue, sessions, student_identity
from app.services.wait_time import WaitTimeService


@pytest.fixture
def as_of(app):
    with app.app_context():
        return db.session.scalar(db.select(db.func.sysdatetimeoffset()))


def history(instructor_id, as_of, *, ended_at=None):
    record = HelpSession(
        instructor_id=instructor_id,
        public_code=student_identity.new_token()[:22],
        status="ended",
        started_at=as_of - timedelta(days=200),
        ended_at=ended_at or as_of - timedelta(seconds=1),
    )
    db.session.add(record)
    db.session.flush()
    return record


def help_record(help_session, seconds, as_of, *, status="completed", completed_at=None):
    finished = completed_at if completed_at is not None else as_of - timedelta(minutes=1)
    started = finished - timedelta(seconds=seconds)
    identity = StudentIdentity(
        public_token_hash=student_identity.token_hash(student_identity.new_token())
    )
    db.session.add(identity)
    db.session.flush()
    record = QueueEntry(
        session_id=help_session.id,
        student_identity_id=identity.id,
        queue_number=help_session.next_queue_number,
        status=status,
        joined_at=started - timedelta(minutes=1),
        service_started_at=started if status != "waiting" else None,
        completed_at=finished if status == "completed" else None,
        left_at=finished if status == "left" else None,
    )
    help_session.next_queue_number += 1
    db.session.add(record)
    db.session.flush()
    return record


@pytest.mark.parametrize("count", [0, 1, 2])
def test_no_or_sparse_history_is_unavailable(app, queue_session, as_of, count):
    with app.app_context():
        current = sessions.owned_session(*queue_session)
        for _ in range(count):
            help_record(current, 120, as_of)
        assert WaitTimeService.estimate_minutes(current, 2, as_of=as_of) is None
        assert WaitTimeService.estimate_minutes(current, 0, as_of=as_of) == 0


@pytest.mark.parametrize("count", [0, 1, 2])
def test_sparse_current_uses_only_instructor_history(app, queue_session, as_of, count):
    with app.app_context():
        current = sessions.owned_session(*queue_session)
        previous = history(queue_session[0], as_of)
        for duration in (90, 150):
            help_record(previous, duration, as_of)
        for _ in range(count):
            help_record(current, 900, as_of)
        assert WaitTimeService.estimate_minutes(current, 3, as_of=as_of) == 6


def test_three_current_completions_override_history_and_use_all_current_samples(
    app, queue_session, as_of
):
    with app.app_context():
        current = sessions.owned_session(*queue_session)
        previous = history(queue_session[0], as_of)
        help_record(previous, 900, as_of)
        for duration in (120, 180, 240):
            help_record(current, duration, as_of)
        assert WaitTimeService.estimate_minutes(current, 2, as_of=as_of) == 6
        help_record(current, 60, as_of)
        assert WaitTimeService.estimate_minutes(current, 2, as_of=as_of) == 5


def test_historical_cutoff_instructor_and_session_end_boundaries(app, queue_session, as_of):
    with app.app_context():
        current = sessions.owned_session(*queue_session)
        previous = history(queue_session[0], as_of)
        cutoff = as_of - timedelta(days=90)
        help_record(previous, 60, as_of, completed_at=cutoff)
        help_record(previous, 900, as_of, completed_at=cutoff - timedelta(microseconds=1))
        # A completion after its recorded session end cannot be trusted.
        help_record(previous, 900, as_of, completed_at=as_of)
        future_session = history(queue_session[0], as_of, ended_at=as_of + timedelta(days=1))
        help_record(future_session, 900, as_of)
        other = register_instructor("wait-other@example.edu", "Other", "a long test password")
        other_history = history(other.id, as_of)
        help_record(other_history, 900, as_of)
        assert WaitTimeService.estimate_minutes(current, 2, as_of=as_of) == 2


@pytest.mark.parametrize("historical", [False, True])
def test_waiting_serving_left_zero_and_future_samples_excluded(
    app, queue_session, as_of, historical
):
    with app.app_context():
        current = sessions.owned_session(*queue_session)
        sample_session = history(queue_session[0], as_of) if historical else current
        help_record(sample_session, 120, as_of)
        help_record(sample_session, 120, as_of)
        for status in ("waiting", "serving", "left"):
            help_record(sample_session, 900, as_of, status=status)
        help_record(sample_session, 0, as_of)
        help_record(sample_session, 900, as_of, completed_at=as_of + timedelta(seconds=1))
        expected = 4 if historical else None  # only two valid current samples, below threshold
        assert WaitTimeService.estimate_minutes(current, 2, as_of=as_of) == expected
        help_record(sample_session, 120, as_of)
        assert WaitTimeService.estimate_minutes(current, 2, as_of=as_of) == 4


@pytest.mark.parametrize(
    "invalid", ["missing_start", "missing_end", "negative", "start_before_join"]
)
def test_database_rejects_malformed_completed_samples(app, queue_session, as_of, invalid):
    with app.app_context():
        current = sessions.owned_session(*queue_session)
        sample = help_record(current, 120, as_of)
        db.session.commit()
        changes = {
            "missing_start": {"service_started_at": None},
            "missing_end": {"completed_at": None},
            "negative": {"completed_at": sample.service_started_at - timedelta(seconds=1)},
            "start_before_join": {"service_started_at": sample.joined_at - timedelta(seconds=1)},
        }[invalid]
        with pytest.raises(IntegrityError):
            db.session.execute(
                db.update(QueueEntry).where(QueueEntry.id == sample.id).values(**changes)
            )
            db.session.commit()
        db.session.rollback()
        assert WaitTimeService.estimate_minutes(current, 1, as_of=as_of) is None


@pytest.mark.parametrize(
    ("durations", "ahead", "minutes"),
    [
        ([30, 30, 30], 1, 1),
        ([30, 30, 30], 3, 2),  # round the product, not each help
        ([60, 60, 60], 1, 1),
        ([60.000001, 60.000001, 60.000001], 1, 2),
        ([30, 60, 90], 4, 4),
    ],
)
def test_round_final_estimate_up_to_minutes(app, queue_session, as_of, durations, ahead, minutes):
    with app.app_context():
        current = sessions.owned_session(*queue_session)
        for duration in durations:
            help_record(current, duration, as_of)
        assert WaitTimeService.estimate_minutes(current, ahead, as_of=as_of) == minutes


def test_serving_counts_as_full_help_and_leaving_removes_only_that_request(
    app, queue_session, as_of
):
    with app.app_context():
        current = sessions.owned_session(*queue_session)
        for _ in range(3):
            help_record(current, 90, as_of)
        db.session.commit()
        first_token, second_token, target_token = [student_identity.new_token() for _ in range(3)]
        first = queue.join(queue_session[1], first_token).id
        second = queue.join(queue_session[1], second_token).id
        queue.join(queue_session[1], target_token)
        assert queue.client_state(queue_session[1], target_token).estimated_wait_minutes == 3
        queue.begin_serving(*queue_session, first)
        # Even a long-running current help contributes one whole expected duration.
        entry = db.session.get(QueueEntry, first)
        entry.joined_at = as_of - timedelta(hours=2)
        entry.service_started_at = as_of - timedelta(hours=1)
        db.session.commit()
        state = queue.client_state(queue_session[1], target_token)
        assert state.people_ahead == 2 and state.estimated_wait_minutes == 3
        assert queue.client_state(queue_session[1], first_token).estimated_wait_minutes is None
        queue.leave(queue_session[1], second_token, second)
        state = queue.client_state(queue_session[1], target_token)
        assert state.people_ahead == 1 and state.estimated_wait_minutes == 2
        queue.leave(queue_session[1], first_token, first)
        state = queue.client_state(queue_session[1], target_token)
        assert state.people_ahead == 0 and state.estimated_wait_minutes == 0


def test_client_page_and_live_fragment_update_estimate_after_done(
    app, queue_session, as_of, hidden_fields
):
    browser = app.test_client()
    url = f"/session/{queue_session[1]}"
    with app.app_context():
        current = sessions.owned_session(*queue_session)
        for _ in range(2):
            help_record(current, 90, as_of)
        db.session.commit()
        first = queue.join(queue_session[1], student_identity.new_token()).id
        queue.join(queue_session[1], student_identity.new_token())
        queue.begin_serving(*queue_session, first)
        entry = db.session.get(QueueEntry, first)
        entry.joined_at = as_of - timedelta(minutes=3)
        entry.service_started_at = as_of - timedelta(minutes=2)
        db.session.commit()
    browser.post(url + "/join", data=hidden_fields(browser.get(url)))
    assert "Not enough completed help history yet" in browser.get(url).text
    with app.app_context():
        queue.complete_current(*queue_session, first)
    for path in (url, url + "/state"):
        response = browser.get(path)
        assert "Estimated wait: About 2 minutes." in response.text
        assert response.headers["Cache-Control"] == "no-store"
    with app.app_context():
        sessions.end_session(*queue_session)
    ended = browser.get(url + "/state")
    assert "Session ended" in ended.text and "Estimated wait:" not in ended.text


def test_zero_ahead_message_and_hidden_estimates_outside_waiting(
    app, queue_session, as_of, hidden_fields
):
    browser = app.test_client()
    url = f"/session/{queue_session[1]}"
    page = browser.get(url)
    assert "Estimated wait:" not in page.text
    browser.post(url + "/join", data=hidden_fields(page))
    assert "No one ahead; waiting for the instructor" in browser.get(url + "/state").text
    with app.app_context():
        entry_id = db.session.scalar(db.select(QueueEntry.id))
        queue.begin_serving(*queue_session, entry_id)
    assert "Estimated wait:" not in browser.get(url + "/state").text
    browser.post(url + "/leave", data=hidden_fields(browser.get(url)))
    assert "Estimated wait:" not in browser.get(url + "/state").text


def test_single_minute_label_and_completed_request_has_no_estimate(
    app, queue_session, as_of, hidden_fields
):
    browser = app.test_client()
    url = f"/session/{queue_session[1]}"
    with app.app_context():
        current = sessions.owned_session(*queue_session)
        for _ in range(3):
            help_record(current, 30, as_of)
        db.session.commit()
        first = queue.join(queue_session[1], student_identity.new_token()).id
    browser.post(url + "/join", data=hidden_fields(browser.get(url)))
    page = browser.get(url + "/state")
    assert "Estimated wait: About 1 minute." in page.text
    assert "About 1 minutes" not in page.text
    target = hidden_fields(page)["entry_id"]
    with app.app_context():
        queue.begin_serving(*queue_session, first)
        queue.complete_current(*queue_session, first)
        queue.complete_current(*queue_session, target)
    completed = browser.get(url + "/state")
    assert "Your request is complete" in completed.text
    assert "Estimated wait:" not in completed.text


def test_negative_ahead_and_naive_time_are_rejected(app, queue_session, as_of):
    with app.app_context():
        current = sessions.owned_session(*queue_session)
        with pytest.raises(ValueError, match="negative"):
            WaitTimeService.estimate_minutes(current, -1, as_of=as_of)
        with pytest.raises(ValueError, match="timezone-aware"):
            WaitTimeService.estimate_minutes(current, 1, as_of=as_of.replace(tzinfo=None))
