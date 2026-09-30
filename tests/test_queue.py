from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy.exc import DataError, IntegrityError

from app.auth.services import register_instructor
from app.extensions import db
from app.models import HelpSession, QueueEntry, StudentIdentity
from app.services import queue, sessions, student_identity


def test_join_is_idempotent_and_identity_is_hash_only(app, queue_session):
    token = student_identity.new_token()
    with app.app_context():
        first = queue.join(queue_session[1], token, "  Optional Name  ")
        identity, number, joined = first.id, first.queue_number, first.joined_at
        again = queue.join(queue_session[1], token, "Different name")
        assert (again.id, again.queue_number, again.joined_at) == (identity, number, joined)
        assert again.display_name == "Optional Name" and again.status == "waiting"
        profile = db.session.get(StudentIdentity, again.student_identity_id)
        assert profile.public_token_hash == student_identity.token_hash(token)
        assert token not in str(profile.__dict__)
        assert sessions.active_session(queue_session[0]).next_queue_number == 2
        assert queue.client_state(queue_session[1], token).people_ahead == 0


def test_leave_preserves_history_and_old_leave_does_not_remove_rejoin(app, queue_session):
    token = student_identity.new_token()
    with app.app_context():
        first = queue.join(queue_session[1], token)
        first_id, joined = first.id, first.joined_at
        left = queue.leave(queue_session[1], token, first_id)
        left_at, updated = left.left_at, left.updated_at
        assert left.status == "left" and left.left_at >= joined
        again = queue.leave(queue_session[1], token, first_id)
        assert (again.left_at, again.updated_at) == (left_at, updated)
        second = queue.join(queue_session[1], token)
        assert second.queue_number == 2 and second.id != first_id
        queue.leave(queue_session[1], token, first_id)
        assert queue.client_state(queue_session[1], token).entry_id == str(second.id)
        assert db.session.get(QueueEntry, first_id).joined_at == joined


def test_repeated_leave_refreshes_cached_state(app, queue_session):
    token = student_identity.new_token()
    with app.app_context():
        cached = queue.join(queue_session[1], token)
        entry_id = cached.id
        assert cached.status == "waiting"
        # A separate request commits while this session retains its loaded object.
        with app.app_context():
            left = queue.leave(queue_session[1], token, entry_id)
            original_times = (left.left_at, left.updated_at)
        assert cached.status == "waiting"
        repeated = queue.leave(queue_session[1], token, entry_id)
        assert repeated.status == "left"
        assert (repeated.left_at, repeated.updated_at) == original_times


def test_positions_ignore_left_entries_and_other_sessions(app, queue_session):
    tokens = [student_identity.new_token() for _ in range(3)]
    with app.app_context():
        entries = [queue.join(queue_session[1], token, "Same name") for token in tokens]
        assert [entry.queue_number for entry in entries] == [1, 2, 3]
        assert queue.client_state(queue_session[1], tokens[2]).people_ahead == 2
        queue.leave(queue_session[1], tokens[0], entries[0].id)
        assert queue.client_state(queue_session[1], tokens[2]).people_ahead == 1
        other = register_instructor("other-queue@example.edu", "Other", "a long test password")
        code = sessions.start_session(other.id).public_code
        entry = queue.join(code, tokens[2])
        assert entry.queue_number == 1
        assert queue.client_state(code, tokens[2]).people_ahead == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(StudentIdentity)) == 3


def test_serving_entries_are_active_and_count_ahead(app, queue_session):
    first_token, second_token = student_identity.new_token(), student_identity.new_token()
    with app.app_context():
        first = queue.join(queue_session[1], first_token)
        first.status = "serving"
        first.service_started_at = db.func.clock_timestamp()
        db.session.commit()
        first_id = first.id
        assert queue.join(queue_session[1], first_token).id == first_id
        queue.join(queue_session[1], second_token)
        assert queue.client_state(queue_session[1], second_token).people_ahead == 1
        queue.leave(queue_session[1], first_token, first_id)
        assert queue.client_state(queue_session[1], second_token).people_ahead == 0
        assert db.session.get(QueueEntry, first_id).service_started_at is not None


@pytest.mark.parametrize("same_browser", [True, False])
def test_concurrent_joins_are_atomic(app, queue_session, same_browser):
    tokens = [student_identity.new_token() for _ in range(4)]
    if same_browser:
        tokens = [tokens[0]] * 4
    barrier = Barrier(4)

    def join(token):
        with app.app_context():
            db.session.execute(db.text("SET LOCAL lock_timeout = '5s'"))
            barrier.wait(timeout=5)
            entry = queue.join(queue_session[1], token)
            return entry.id, entry.queue_number

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(join, tokens))
    with app.app_context():
        expected = 1 if same_browser else 4
        assert len(set(results)) == expected
        assert sorted({number for _, number in results}) == list(range(1, expected + 1))
        assert sessions.active_session(queue_session[0]).next_queue_number == expected + 1
        assert (
            db.session.scalar(db.select(db.func.count()).select_from(StudentIdentity)) == expected
        )


def test_first_identity_creation_across_sessions_is_unique(app, queue_session):
    with app.app_context():
        owner = register_instructor("parallel@example.edu", "Parallel", "a long test password")
        second_code = sessions.start_session(owner.id).public_code
    token, barrier = student_identity.new_token(), Barrier(2)

    def join(code):
        with app.app_context():
            db.session.execute(db.text("SET LOCAL lock_timeout = '5s'"))
            barrier.wait(timeout=5)
            return queue.join(code, token).student_identity_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        identities = list(pool.map(join, [queue_session[1], second_code]))
    assert identities[0] == identities[1]


def test_end_blocks_joins_and_leaves_but_preserves_unfinished_history(app, queue_session):
    token = student_identity.new_token()
    with app.app_context():
        entry = queue.join(queue_session[1], token)
        entry_id, joined = entry.id, entry.joined_at
        sessions.end_session(*queue_session)
        with pytest.raises(sessions.SessionEnded):
            queue.join(queue_session[1], student_identity.new_token())
        with pytest.raises(sessions.SessionEnded):
            queue.leave(queue_session[1], token, entry_id)
        assert queue.client_state(queue_session[1], token).status == "ended"
        saved = db.session.get(QueueEntry, entry_id)
        assert saved.status == "waiting" and saved.joined_at == joined and saved.left_at is None
        assert db.session.scalar(db.select(db.func.count()).select_from(StudentIdentity)) == 1


def test_join_racing_end_has_one_consistent_outcome(app, queue_session):
    barrier, token = Barrier(2), student_identity.new_token()

    def action(is_join):
        with app.app_context():
            db.session.execute(db.text("SET LOCAL lock_timeout = '5s'"))
            barrier.wait(timeout=5)
            if not is_join:
                sessions.end_session(*queue_session)
                return "ended"
            try:
                queue.join(queue_session[1], token)
                return "joined"
            except sessions.SessionEnded:
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(action, [True, False]))
    with app.app_context():
        state = queue.client_state(queue_session[1], token)
        assert state.status == "ended"
        expected = int(results[0] == "joined")
        assert db.session.scalar(db.select(db.func.count()).select_from(QueueEntry)) == expected
        assert db.session.scalar(db.select(HelpSession.next_queue_number)) == expected + 1


def test_failed_insert_rolls_back_number_and_identity(app, queue_session, monkeypatch):
    token = student_identity.new_token()
    with app.app_context():
        # Fail after allocation to verify that the transaction owns all related writes.
        with monkeypatch.context() as scoped:
            scoped.setattr(
                db.session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("fail"))
            )
            with pytest.raises(RuntimeError):
                queue.join(queue_session[1], token)
        assert sessions.active_session(queue_session[0]).next_queue_number == 1
        assert student_identity.find_identity(token) is None
        assert queue.join(queue_session[1], token).queue_number == 1


def test_leave_cannot_target_other_identity_or_session(app, queue_session):
    first_token, other_token = student_identity.new_token(), student_identity.new_token()
    with app.app_context():
        entry = queue.join(queue_session[1], first_token)
        entry_id = entry.id
        queue.join(queue_session[1], other_token)
        with pytest.raises(queue.EntryNotFound):
            queue.leave(queue_session[1], other_token, entry_id)
        assert db.session.get(QueueEntry, entry_id).status == "waiting"
        owner = register_instructor("scope@example.edu", "Scope", "a long test password")
        second_code = sessions.start_session(owner.id).public_code
        queue.join(second_code, first_token)
        with pytest.raises(queue.EntryNotFound):
            queue.leave(second_code, first_token, entry_id)


@pytest.mark.parametrize("status", ["waiting", "serving"])
def test_partial_unique_index_covers_both_active_states(app, queue_session, status):
    token = student_identity.new_token()
    with app.app_context():
        entry = queue.join(queue_session[1], token)
        if status == "serving":
            entry.status = status
            entry.service_started_at = db.func.clock_timestamp()
            db.session.commit()
        values = {
            "session_id": entry.session_id,
            "student_identity_id": entry.student_identity_id,
            "queue_number": 2,
        }
        with pytest.raises(IntegrityError) as error:
            db.session.execute(QueueEntry.__table__.insert().values(**values))
            db.session.commit()
        assert error.value.orig.diag.constraint_name == "uq_queue_entry_active_identity"
        db.session.rollback()
        queue.leave(queue_session[1], token, entry.id)
        assert queue.join(queue_session[1], token).queue_number == 2


def test_database_queue_numbers_unique_even_for_history(app, queue_session):
    token = student_identity.new_token()
    with app.app_context():
        first = queue.join(queue_session[1], token)
        first_id, session_id, identity_id = first.id, first.session_id, first.student_identity_id
        queue.leave(queue_session[1], token, first_id)
        with pytest.raises(IntegrityError) as error:
            db.session.execute(
                QueueEntry.__table__.insert().values(
                    session_id=session_id,
                    student_identity_id=identity_id,
                    queue_number=1,
                )
            )
            db.session.commit()
        assert error.value.orig.diag.constraint_name == "uq_queue_entry_session_number"
        db.session.rollback()


@pytest.mark.parametrize(
    "changes",
    [
        {"queue_number": 0},
        {"queue_number": None},
        {"session_id": None},
        {"student_identity_id": None},
        {"student_identity_id": uuid4()},
        {"status": "invalid"},
        {"status": "serving"},
        {"status": "completed"},
        {"status": "left"},
        {"display_name": " "},
        {"display_name": "x" * 101},
        {
            "status": "left",
            "joined_at": datetime.now(UTC),
            "left_at": datetime.now(UTC) - timedelta(days=1),
        },
    ],
)
def test_database_queue_constraints(app, queue_session, changes):
    with app.app_context():
        identity = student_identity.identity_for_join(student_identity.new_token())
        session_id = sessions.active_session(queue_session[0]).id
        values = {"session_id": session_id, "student_identity_id": identity.id, "queue_number": 1}
        db.session.commit()
        values.update(changes)
        with pytest.raises((IntegrityError, DataError)):
            db.session.execute(QueueEntry.__table__.insert().values(**values))
            db.session.commit()
        db.session.rollback()


def test_retention_can_unlink_token_without_deleting_history(app, queue_session):
    token = student_identity.new_token()
    with app.app_context():
        entry = queue.join(queue_session[1], token, "Optional name")
        entry_id = entry.id
        db.session.get(StudentIdentity, entry.student_identity_id).public_token_hash = None
        entry.display_name = None
        db.session.commit()
        assert queue.client_state(queue_session[1], token).status == "not_joined"
        assert db.session.get(QueueEntry, entry_id).queue_number == 1
