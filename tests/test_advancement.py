from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.auth.services import register_instructor
from app.extensions import db
from app.models import QueueEntry
from app.services import queue, sessions, student_identity


def join(code, name=None):
    token = student_identity.new_token()
    return queue.join(code, token, name).id, token


def test_start_done_and_last_completion_preserve_timestamps_and_numbers(app, queue_session):
    with app.app_context():
        first, token = join(queue_session[1])
        second, _ = join(queue_session[1])
        assert queue.begin_serving(*queue_session, first)
        started = db.session.get(QueueEntry, first).service_started_at
        assert started >= db.session.get(QueueEntry, first).joined_at
        assert started.utcoffset().total_seconds() == 0
        assert queue.client_state(queue_session[1], token).status == "serving"
        assert not queue.begin_serving(*queue_session, first)
        assert not queue.begin_serving(*queue_session, second)
        assert queue.complete_current(*queue_session, first)
        completed = db.session.get(QueueEntry, first)
        assert completed.status == "completed" and completed.service_started_at == started
        assert completed.completed_at >= started and completed.left_at is None
        completed_at, updated_at = completed.completed_at, completed.updated_at
        assert db.session.get(QueueEntry, second).service_started_at == completed_at
        assert queue.client_state(queue_session[1], token).status == "completed"
        assert not queue.complete_current(*queue_session, first)
        assert (completed.completed_at, completed.updated_at) == (completed_at, updated_at)
        state = queue.master_state(*queue_session)
        assert state.serving.id == second and state.next_up is None and state.waiting_count == 0
        assert queue.complete_current(*queue_session, second)
        assert queue.master_state(*queue_session).serving is None
        rejoined = queue.join(queue_session[1], token)
        assert rejoined.queue_number == 3 and rejoined.status == "waiting"


def test_empty_done_and_waiting_without_serving_are_safe(app, queue_session):
    with app.app_context():
        for operation in (queue.begin_serving, queue.complete_current):
            assert not operation(*queue_session, uuid4())
        first, _ = join(queue_session[1])
        assert not queue.complete_current(*queue_session, first)
        state = queue.master_state(*queue_session)
        assert state.serving is None and state.next_up.id == first and state.waiting_count == 1
        assert db.session.get(QueueEntry, first).service_started_at is None


def test_snapshot_truncates_and_excludes_left_completed_and_other_sessions(app, queue_session):
    with app.app_context():
        entries = [join(queue_session[1], f"Name {index}") for index in range(9)]
        queue.begin_serving(*queue_session, entries[0][0])
        queue.complete_current(*queue_session, entries[0][0])
        queue.leave(queue_session[1], entries[2][1], entries[2][0])
        other = register_instructor("other-master@example.edu", "Other", "a long test password")
        other_code = sessions.start_session(other.id).public_code
        other_id, _ = join(other_code, "Other session")
        queue.begin_serving(other.id, other_code, other_id)
        state = queue.master_state(*queue_session)
        assert state.serving.queue_number == 2
        assert state.next_up.queue_number == 4
        assert [entry.queue_number for entry in state.waiting] == [4, 5, 6, 7, 8]
        assert state.waiting_count == 6
        assert queue.master_state(other.id, other_code).serving.queue_number == 1
        assert queue.complete_current(*queue_session, entries[1][0])
        assert queue.master_state(*queue_session).serving.queue_number == 4


def test_stale_serve_next_does_not_skip_or_replace_a_request(app, queue_session):
    with app.app_context():
        first, token = join(queue_session[1])
        second, _ = join(queue_session[1])
        assert not queue.begin_serving(*queue_session, second)
        queue.leave(queue_session[1], token, first)
        assert not queue.begin_serving(*queue_session, first)
        assert queue.master_state(*queue_session).serving is None
        assert queue.begin_serving(*queue_session, second)


def test_serving_student_leaving_requires_explicit_start_again(app, queue_session):
    with app.app_context():
        first, token = join(queue_session[1])
        second, _ = join(queue_session[1])
        queue.begin_serving(*queue_session, first)
        started = db.session.get(QueueEntry, first).service_started_at
        queue.leave(queue_session[1], token, first)
        assert not queue.complete_current(*queue_session, first)
        state = queue.master_state(*queue_session)
        assert state.serving is None and state.next_up.id == second
        assert db.session.get(QueueEntry, first).service_started_at == started
        assert db.session.get(QueueEntry, first).completed_at is None
        assert queue.begin_serving(*queue_session, second)


def test_ended_session_preserves_unfinished_service_and_rejects_advancement(app, queue_session):
    with app.app_context():
        first, token = join(queue_session[1])
        second, _ = join(queue_session[1])
        queue.begin_serving(*queue_session, first)
        started = db.session.get(QueueEntry, first).service_started_at
        sessions.end_session(*queue_session)
        for operation in (queue.begin_serving, queue.complete_current):
            with pytest.raises(sessions.SessionEnded):
                operation(*queue_session, first)
        state = queue.master_state(*queue_session)
        assert state.status == "ended" and state.serving is None and not state.waiting
        assert db.session.get(QueueEntry, first).service_started_at == started
        assert db.session.get(QueueEntry, first).completed_at is None
        assert db.session.get(QueueEntry, second).status == "waiting"
        assert queue.client_state(queue_session[1], token).status == "ended"


def test_ownership_and_cross_session_targets(app, queue_session):
    with app.app_context():
        first, _ = join(queue_session[1])
        owner = register_instructor("separate@example.edu", "Separate", "a long test password")
        other_id = owner.id
        other_code = sessions.start_session(other_id).public_code
        other_entry, _ = join(other_code)
        for operation in (queue.begin_serving, queue.complete_current):
            with pytest.raises(sessions.SessionNotFound):
                operation(other_id, queue_session[1], first)
            with pytest.raises(sessions.SessionNotFound):
                operation(queue_session[0], "unknown", first)
            assert not operation(*queue_session, other_entry)
            with pytest.raises(queue.EntryNotFound):
                operation(*queue_session, "not-a-uuid")
        with pytest.raises(sessions.SessionNotFound):
            queue.master_state(other_id, queue_session[1])
        assert queue.master_state(*queue_session).serving is None


@pytest.mark.parametrize("complete", [False, True])
def test_concurrent_identical_actions_transition_only_once(app, queue_session, complete):
    with app.app_context():
        first, _ = join(queue_session[1])
        second, _ = join(queue_session[1])
        if complete:
            queue.begin_serving(*queue_session, first)
    barrier = Barrier(2)

    def advance(_):
        with app.app_context():
            db.session.execute(db.text("SET LOCAL lock_timeout = '5s'"))
            barrier.wait(timeout=5)
            operation = queue.complete_current if complete else queue.begin_serving
            return operation(*queue_session, first)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(advance, range(2))) == [False, True]
    with app.app_context():
        state = queue.master_state(*queue_session)
        assert state.serving.id == (second if complete else first)
        assert db.session.get(QueueEntry, second).completed_at is None


@pytest.mark.parametrize("competing_action", ["leave", "end", "join"])
def test_done_serializes_with_other_queue_mutations(app, queue_session, competing_action):
    with app.app_context():
        first, token = join(queue_session[1])
        second, _ = join(queue_session[1])
        queue.begin_serving(*queue_session, first)
    barrier = Barrier(2)

    def action(is_done):
        with app.app_context():
            db.session.execute(db.text("SET LOCAL lock_timeout = '5s'"))
            barrier.wait(timeout=5)
            if is_done:
                try:
                    return queue.complete_current(*queue_session, first)
                except sessions.SessionEnded:
                    return False
            if competing_action == "leave":
                queue.leave(queue_session[1], token, first)
            elif competing_action == "end":
                sessions.end_session(*queue_session)
            else:
                join(queue_session[1])

    with ThreadPoolExecutor(max_workers=2) as pool:
        changed, _ = list(pool.map(action, [True, False]))
    with app.app_context():
        current = db.session.get(QueueEntry, first)
        following = db.session.get(QueueEntry, second)
        assert (current.status == "completed") == changed
        assert (following.status == "serving") == changed
        assert (current.completed_at is not None) == changed
        if competing_action == "leave":
            assert (current.left_at is not None) == (not changed)
        if competing_action == "end":
            assert queue.master_state(*queue_session).status == "ended"
        if competing_action == "join":
            assert sessions.owned_session(*queue_session).next_queue_number == 4


def test_failed_promotion_rolls_back_completion(app, queue_session, monkeypatch):
    with app.app_context():
        first, _ = join(queue_session[1])
        second, _ = join(queue_session[1])
        queue.begin_serving(*queue_session, first)
        with monkeypatch.context() as patch:

            def fail_commit():
                raise RuntimeError("commit failed")

            patch.setattr(db.session, "commit", fail_commit)
            with pytest.raises(RuntimeError):
                queue.complete_current(*queue_session, first)
        assert db.session.get(QueueEntry, first).status == "serving"
        assert db.session.get(QueueEntry, first).completed_at is None
        assert db.session.get(QueueEntry, second).status == "waiting"
        assert queue.complete_current(*queue_session, first)


def test_database_allows_only_one_serving_entry_per_session(app, queue_session):
    with app.app_context():
        first, _ = join(queue_session[1])
        second, _ = join(queue_session[1])
        queue.begin_serving(*queue_session, first)
        with pytest.raises(IntegrityError) as error:
            db.session.execute(
                db.update(QueueEntry)
                .where(QueueEntry.id == second)
                .values(status="serving", service_started_at=db.func.clock_timestamp())
            )
            db.session.commit()
        assert error.value.orig.diag.constraint_name == "uq_queue_entry_serving_session"
        db.session.rollback()


def test_done_refreshes_cached_state_after_another_master_advances(app, queue_session):
    with app.app_context():
        first, _ = join(queue_session[1])
        second, _ = join(queue_session[1])
        queue.begin_serving(*queue_session, first)
        cached = db.session.get(QueueEntry, first)
        with app.app_context():
            queue.complete_current(*queue_session, first)
            completed_at = db.session.get(QueueEntry, first).completed_at
        assert cached.status == "serving"
        assert not queue.complete_current(*queue_session, first)
        assert db.session.get(QueueEntry, first).completed_at == completed_at
        assert queue.master_state(*queue_session).serving.id == second
