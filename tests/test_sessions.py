import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.auth.services import register_instructor
from app.extensions import db
from app.models import HelpSession, Instructor
from app.services import sessions

pytestmark = pytest.mark.usefixtures("auth_db")


@pytest.fixture
def actors(app):
    with app.app_context():
        owner = register_instructor("owner@example.edu", "Owner", "a sufficiently long password")
        other = register_instructor("other@example.edu", "Other", "a sufficiently long password")
        return owner.id, other.id


@pytest.fixture
def public_code(app, actors):
    with app.app_context():
        return sessions.start_session(actors[0]).public_code


@pytest.fixture
def browser(app):
    def authenticated(identity):
        client = app.test_client()
        with client.session_transaction() as state:
            state["_user_id"] = str(identity)
            state["_fresh"] = True
        return client

    return authenticated


def test_session_lifecycle_and_duplicate_actions(app, actors):
    owner, other = actors
    with app.app_context():
        assert sessions.active_session(owner) is None
        first = sessions.start_session(owner)
        assert isinstance(first.id, UUID)
        assert re.fullmatch(r"[A-Za-z0-9_-]{22}", first.public_code)
        assert first.public_code != str(first.id)
        assert first.instructor_id == owner
        assert first.status == "active" and first.ended_at is None
        assert first.next_queue_number == 1
        assert first.started_at.utcoffset().total_seconds() == 0
        assert first.accepts_joins
        assert sessions.active_session(other) is None
        assert sessions.start_session(owner).id == first.id
        identity, code, started = first.id, first.public_code, first.started_at
        ended = sessions.end_session(owner, code)
        assert ended.status == "ended" and not ended.accepts_joins
        assert ended.ended_at >= started
        ended_at, updated_at = ended.ended_at, ended.updated_at
        repeated = sessions.end_session(owner, code)
        assert (repeated.id, repeated.started_at, repeated.ended_at, repeated.updated_at) == (
            identity,
            started,
            ended_at,
            updated_at,
        )
        assert sessions.active_session(owner) is None
        second = sessions.start_session(owner)
        assert second.id != identity and second.public_code != code
        sessions.end_session(owner, code)
        assert sessions.active_session(owner).id == second.id
        assert db.session.scalar(db.select(db.func.count()).select_from(HelpSession)) == 2


def test_concurrent_starts_return_one_session(app, actors):
    barrier = Barrier(2)

    def start(_):
        with app.app_context():
            db.session.execute(db.text("SET LOCAL lock_timeout = '5s'"))
            barrier.wait(timeout=5)
            return sessions.start_session(actors[0]).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        identities = list(pool.map(start, range(2)))
    assert identities[0] == identities[1]
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(HelpSession)) == 1


def test_concurrent_ends_preserve_first_timestamp(app, actors, public_code):
    barrier = Barrier(2)

    def end(_):
        with app.app_context():
            db.session.execute(db.text("SET LOCAL lock_timeout = '5s'"))
            barrier.wait(timeout=5)
            result = sessions.end_session(actors[0], public_code)
            return result.ended_at, result.updated_at

    with ThreadPoolExecutor(max_workers=2) as pool:
        times = list(pool.map(end, range(2)))
    assert times[0] == times[1]


def test_services_enforce_ownership(app, actors, public_code):
    with app.app_context():
        for operation in (sessions.owned_session, sessions.end_session):
            with pytest.raises(sessions.SessionNotFound):
                operation(actors[1], public_code)
        assert sessions.owned_session(actors[0], public_code).status == "active"
        other = sessions.start_session(actors[1])
        assert other.public_code != public_code
        assert sessions.active_session(actors[1]).id == other.id


def test_missing_sessions_and_inactive_instructors_are_rejected(app, actors):
    with app.app_context():
        for operation in (sessions.owned_session, sessions.end_session):
            with pytest.raises(sessions.SessionNotFound):
                operation(actors[0], "missing")
        with pytest.raises(sessions.SessionNotFound):
            sessions.session_for_join("missing")
        db.session.rollback()
        with pytest.raises(sessions.SessionNotFound):
            sessions.start_session(uuid4())
        db.session.get(Instructor, actors[0]).is_active = False
        db.session.commit()
        with pytest.raises(sessions.SessionNotFound):
            sessions.start_session(actors[0])


def test_join_guard_rejects_ended_session_and_refreshes_stale_state(app, actors, public_code):
    with app.app_context():
        stale = sessions.owned_session(actors[0], public_code)
        assert stale.accepts_joins

        def end_elsewhere():
            with app.app_context():
                sessions.end_session(actors[0], public_code)

        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(end_elsewhere).result(timeout=5)
        with pytest.raises(sessions.SessionEnded):
            sessions.session_for_join(public_code)
        assert not stale.accepts_joins
        db.session.rollback()


def test_join_guard_holds_row_lock_until_caller_finishes(app, public_code):
    def competing_lock():
        with app.app_context():
            try:
                db.session.execute(
                    db.select(HelpSession)
                    .where(HelpSession.public_code == public_code)
                    .with_for_update(nowait=True)
                )
            except OperationalError as error:
                return error.orig.sqlstate
            return "unlocked"

    with app.app_context():
        assert sessions.session_for_join(public_code).accepts_joins
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(competing_lock).result(timeout=5) == "55P03"
        db.session.rollback()
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(competing_lock).result(timeout=5) == "unlocked"


def test_public_code_collision_is_retried(app, actors, public_code, monkeypatch):
    codes = iter([public_code, "B" * 22])
    monkeypatch.setattr(sessions.secrets, "token_urlsafe", lambda _: next(codes))
    with app.app_context():
        other = sessions.start_session(actors[1])
        assert other.public_code == "B" * 22


def test_exhausted_code_collisions_roll_back(app, actors, public_code, monkeypatch):
    monkeypatch.setattr(sessions.secrets, "token_urlsafe", lambda _: public_code)
    with app.app_context():
        with pytest.raises(RuntimeError, match="unique session code"):
            sessions.start_session(actors[1])
        assert sessions.active_session(actors[1]) is None
        assert sessions.active_session(actors[0]).public_code == public_code


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "invalid"},
        {"status": None},
        {"status": "ended"},
        {"ended_at": datetime.now(UTC)},
        {"next_queue_number": 0},
        {"next_queue_number": None},
        {"instructor_id": None},
        {"instructor_id": uuid4()},
        {"public_code": "bad code"},
        {"public_code": None},
        {"started_at": None},
        {
            "status": "ended",
            "started_at": datetime.now(UTC),
            "ended_at": datetime.now(UTC) - timedelta(days=1),
        },
    ],
)
def test_database_rejects_invalid_session_state(app, actors, changes):
    values = {"id": uuid4(), "instructor_id": actors[0], "public_code": "A" * 22}
    values.update(changes)
    with app.app_context():
        with pytest.raises(IntegrityError):
            db.session.execute(HelpSession.__table__.insert().values(**values))
            db.session.commit()
        db.session.rollback()


def test_database_enforces_one_active_session_and_unique_code(app, actors, public_code):
    with app.app_context():
        for owner, code, constraint in (
            (actors[0], "B" * 22, "uq_help_session_active_instructor"),
            (actors[1], public_code, "uq_help_session_public_code"),
        ):
            with pytest.raises(IntegrityError) as error:
                db.session.execute(
                    HelpSession.__table__.insert().values(
                        id=uuid4(),
                        instructor_id=owner,
                        public_code=code,
                    )
                )
                db.session.commit()
            assert error.value.orig.diag.constraint_name == constraint
            db.session.rollback()


def test_instructor_deletion_cannot_remove_session_history(app, actors, public_code):
    with app.app_context():
        with pytest.raises(IntegrityError):
            db.session.execute(db.delete(Instructor).where(Instructor.id == actors[0]))
            db.session.commit()
        db.session.rollback()
        assert sessions.owned_session(actors[0], public_code).public_code == public_code


def test_dashboard_start_master_and_end_forms(app, actors, browser, csrf_token):
    client = browser(actors[0])
    dashboard = client.get("/instructor/dashboard")
    assert "No active help session" in dashboard.text
    response = client.post(
        "/instructor/sessions",
        data={
            "csrf_token": csrf_token(dashboard),
            "instructor_id": str(actors[1]),
        },
    )
    assert response.status_code == 302
    master_url = response.location
    with app.app_context():
        current = sessions.active_session(actors[0])
        assert current and sessions.active_session(actors[1]) is None
        assert str(current.id) not in master_url
        assert current.public_code in master_url
        code, identity = current.public_code, current.id
    master = client.get(master_url)
    assert "Session active" in master.text
    assert str(identity) not in master.text
    dashboard = client.get("/instructor/dashboard")
    assert "Active help session" in dashboard.text and code in dashboard.text
    repeated = client.post("/instructor/sessions", data={"csrf_token": csrf_token(dashboard)})
    assert repeated.location == master_url
    assert client.get("/instructor/sessions").status_code == 405
    end_url = f"/instructor/sessions/{code}/end"
    assert client.get(end_url).status_code == 405
    assert client.post(end_url, data={"csrf_token": csrf_token(master)}).location == master_url
    ended = client.get(master_url)
    assert "Session ended" in ended.text
    assert "End session</button>" not in ended.text
    assert "No active help session" in client.get("/instructor/dashboard").text


def test_other_instructor_cannot_view_end_or_find_session_on_dashboard(
    app, actors, public_code, browser, csrf_token
):
    client = browser(actors[1])
    dashboard = client.get("/instructor/dashboard")
    assert public_code not in dashboard.text
    assert client.get(f"/instructor/sessions/{public_code}/master").status_code == 404
    response = client.post(
        f"/instructor/sessions/{public_code}/end",
        data={
            "csrf_token": csrf_token(dashboard),
            "instructor_id": str(actors[0]),
        },
    )
    assert response.status_code == 404
    with app.app_context():
        assert sessions.owned_session(actors[0], public_code).status == "active"


def test_anonymous_session_requests_redirect_to_login(client, public_code, csrf_token):
    token = csrf_token(client.get("/auth/login"))
    for path in ("/instructor/sessions", f"/instructor/sessions/{public_code}/end"):
        response = client.post(path, data={"csrf_token": token})
        assert response.status_code == 302 and "/auth/login" in response.location
    response = client.get(f"/instructor/sessions/{public_code}/master")
    assert response.status_code == 302 and "/auth/login" in response.location


def test_csrf_required_for_session_mutations(app, actors, public_code, browser):
    client = browser(actors[0])
    for path in ("/instructor/sessions", f"/instructor/sessions/{public_code}/end"):
        assert client.post(path).status_code == 400
        assert client.post(path, data={"csrf_token": "bad"}).status_code == 400
    with app.app_context():
        assert sessions.owned_session(actors[0], public_code).status == "active"
        assert db.session.scalar(db.select(db.func.count()).select_from(HelpSession)) == 1


def test_multiple_master_browsers_read_current_state(actors, public_code, browser, csrf_token):
    first, second = browser(actors[0]), browser(actors[0])
    master_url = f"/instructor/sessions/{public_code}/master"
    assert "Session active" in first.get(master_url).text
    page = second.get(master_url)
    response = second.post(
        f"/instructor/sessions/{public_code}/end",
        data={
            "csrf_token": csrf_token(page),
        },
    )
    assert response.location == master_url
    assert "Session ended" in first.get(master_url).text


def test_unknown_session_routes_return_404(actors, browser, csrf_token):
    client = browser(actors[0])
    token = csrf_token(client.get("/instructor/dashboard"))
    assert client.get("/instructor/sessions/unknown/master").status_code == 404
    assert (
        client.post("/instructor/sessions/unknown/end", data={"csrf_token": token}).status_code
        == 404
    )
