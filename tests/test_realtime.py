from unittest.mock import patch

import pytest

from app import create_app
from app.auth.services import register_instructor
from app.extensions import db
from app.models import HelpSession, Instructor, QueueEntry, StudentIdentity
from app.services import queue, sessions, student_identity


@pytest.fixture
def live_browser(app, queue_session, csrf_token):
    sockets = []

    def connect(*, view="client", owner=None, code=None, overrides=None, headers=None):
        code = code or queue_session[1]
        browser = app.test_client()
        if owner:
            with browser.session_transaction() as state:
                state["_user_id"] = str(owner)
                state["_fresh"] = True
        page = browser.get(f"/session/{code}")
        # Unknown sessions still need a valid CSRF token to exercise authorization.
        if page.status_code != 200:
            page = browser.get("/auth/login")
        auth = {"view": view, "public_code": code, "csrf_token": csrf_token(page)}
        auth.update(overrides or {})
        socket = app.extensions["socketio"].test_client(
            app,
            flask_test_client=browser,
            auth=auth,
            headers=headers,
        )
        sockets.append(socket)
        return browser, socket

    yield connect
    for socket in sockets:
        if socket.is_connected():
            socket.disconnect()


def notices(socket):
    received = socket.get_received()
    for message in received:
        assert message == {"name": "queue_changed", "args": [{}], "namespace": "/"}
    return len(received)


def test_join_leave_advance_end_notify_both_masters_and_clients(app, queue_session, live_browser):
    _, first_master = live_browser(view="master", owner=queue_session[0])
    _, second_master = live_browser(view="master", owner=queue_session[0])
    _, student = live_browser()
    listeners = (first_master, second_master, student)
    assert all(socket.is_connected() for socket in listeners)
    with app.app_context():
        token = student_identity.new_token()
        first = queue.join(queue_session[1], token).id
        assert all(notices(socket) == 1 for socket in listeners)
        queue.join(queue_session[1], token)  # idempotent retry is not a queue transition
        assert all(notices(socket) == 0 for socket in listeners)
        queue.begin_serving(*queue_session, first)
        assert all(notices(socket) == 1 for socket in listeners)
        queue.complete_current(*queue_session, first)
        assert all(notices(socket) == 1 for socket in listeners)
        queue.complete_current(*queue_session, first)
        assert all(notices(socket) == 0 for socket in listeners)
        second = queue.join(queue_session[1], token).id
        assert all(notices(socket) == 1 for socket in listeners)
        queue.leave(queue_session[1], token, second)
        assert all(notices(socket) == 1 for socket in listeners)
        queue.leave(queue_session[1], token, second)
        assert all(notices(socket) == 0 for socket in listeners)
        sessions.end_session(*queue_session)
        assert all(notices(socket) == 1 for socket in listeners)
        sessions.end_session(*queue_session)
        assert all(notices(socket) == 0 for socket in listeners)


@pytest.mark.parametrize("operation", ["join", "leave", "serve", "done", "end"])
def test_every_notice_follows_a_visible_database_commit(app, queue_session, operation):
    with app.app_context():
        token = student_identity.new_token()
        entry_id = queue.join(queue_session[1], token).id if operation != "join" else None
        if operation == "done":
            queue.begin_serving(*queue_session, entry_id)
        observed = []

        def observe(*args, **kwargs):
            # A separate connection cannot see uncommitted changes.
            with db.engine.connect() as connection:
                model = HelpSession if operation == "end" else QueueEntry
                observed.append(connection.scalar(db.select(model.status)))

        with patch.object(app.extensions["socketio"], "emit", side_effect=observe):
            if operation == "join":
                queue.join(queue_session[1], token)
            elif operation == "leave":
                queue.leave(queue_session[1], token, entry_id)
            elif operation == "serve":
                queue.begin_serving(*queue_session, entry_id)
            elif operation == "done":
                queue.complete_current(*queue_session, entry_id)
            else:
                sessions.end_session(*queue_session)
        expected = {
            "join": "waiting",
            "leave": "left",
            "serve": "serving",
            "done": "completed",
            "end": "ended",
        }[operation]
        assert observed == [expected, expected]


@pytest.mark.parametrize("operation", ["join", "leave", "serve", "done", "end"])
def test_rollback_never_emits(app, queue_session, live_browser, monkeypatch, operation):
    _, socket = live_browser()
    with app.app_context():
        token = student_identity.new_token()
        entry_id = queue.join(queue_session[1], token).id if operation != "join" else None
        if operation == "done":
            queue.begin_serving(*queue_session, entry_id)
        notices(socket)
        with monkeypatch.context() as scoped:

            def failed_commit():
                raise RuntimeError("commit failed")

            scoped.setattr(db.session, "commit", failed_commit)
            with pytest.raises(RuntimeError):
                if operation == "join":
                    queue.join(queue_session[1], token)
                elif operation == "leave":
                    queue.leave(queue_session[1], token, entry_id)
                elif operation == "serve":
                    queue.begin_serving(*queue_session, entry_id)
                elif operation == "done":
                    queue.complete_current(*queue_session, entry_id)
                else:
                    sessions.end_session(*queue_session)
        assert notices(socket) == 0


def test_delivery_failure_preserves_commit_and_does_not_log_secrets(app, queue_session, caplog):
    with app.app_context():
        with patch.object(app.extensions["socketio"], "emit", side_effect=RuntimeError("secret")):
            entry = queue.join(queue_session[1], student_identity.new_token(), "Private name")
        assert db.session.get(QueueEntry, entry.id).status == "waiting"
        assert "Queue update delivery failed" in caplog.text
        assert "secret" not in caplog.text and "Private name" not in caplog.text


@pytest.mark.parametrize(
    "overrides",
    [
        {"csrf_token": None},
        {"csrf_token": "invalid"},
        {"csrf_token": []},
        {"view": "arbitrary-room"},
        {"view": []},
        {"public_code": []},
        {"public_code": "A" * 22},
        {"public_code": "x" * 1000},
    ],
)
def test_bad_socket_subscriptions_are_rejected(live_browser, overrides):
    _, socket = live_browser(overrides=overrides)
    assert not socket.is_connected()


def test_master_room_requires_current_active_owner(app, queue_session, live_browser):
    _, anonymous = live_browser(view="master")
    assert not anonymous.is_connected()
    with app.app_context():
        other_id = register_instructor("socket-other@example.edu", "Other", "a long password!").id
    _, other = live_browser(view="master", owner=other_id)
    assert not other.is_connected()
    with app.app_context():
        db.session.get(Instructor, queue_session[0]).is_active = False
        db.session.commit()
    _, inactive = live_browser(view="master", owner=queue_session[0])
    assert not inactive.is_connected()


def test_cross_origin_and_missing_auth_are_rejected(app, live_browser):
    _, socket = live_browser(headers={"Origin": "https://evil.example"})
    assert not socket.is_connected()
    missing = app.extensions["socketio"].test_client(app)
    assert not missing.is_connected()
    response = app.test_client().get(
        "/socket.io/?EIO=4&transport=polling", headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 400


def test_session_rooms_do_not_cross_and_clients_cannot_choose_rooms_or_mutate(
    app, queue_session, live_browser
):
    with app.app_context():
        owner = register_instructor("socket-scope@example.edu", "Other", "a long password!")
        other_code = sessions.start_session(owner.id).public_code
    _, first = live_browser(overrides={"room": f"master:{other_code}"})
    _, other = live_browser(code=other_code)
    first.emit("join_room", {"room": f"session:{other_code}"})
    for event in ("join", "leave", "done", "advance", "end_session", "queue_changed"):
        first.emit(event, {"public_code": other_code})
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(QueueEntry)) == 0
        queue.join(other_code, student_identity.new_token())
    assert notices(first) == 0 and notices(other) == 1


def test_state_endpoints_are_private_current_and_survive_logout(
    app, queue_session, live_browser, hidden_fields, csrf_token
):
    alice, alice_socket = live_browser()
    bob, bob_socket = live_browser()
    master, master_socket = live_browser(view="master", owner=queue_session[0])
    client_url = f"/session/{queue_session[1]}"
    master_url = f"/instructor/sessions/{queue_session[1]}"
    for browser, name in ((alice, "Alice private"), (bob, "Bob private")):
        form = hidden_fields(browser.get(client_url))
        assert (
            browser.post(client_url + "/join", data={**form, "display_name": name}).status_code
            == 303
        )
    alice_state, bob_state = alice.get(client_url + "/state"), bob.get(client_url + "/state")
    assert "Alice private" in alice_state.text and "Bob private" not in alice_state.text
    assert "Bob private" in bob_state.text and "Alice private" not in bob_state.text
    assert "People ahead: 1" in bob_state.text
    for state in (alice_state, bob_state):
        assert state.headers["Cache-Control"] == "no-store"
        assert "instructor/" not in state.text and "<script" not in state.text
    page = master.get(master_url + "/state")
    assert "Alice private" in page.text and "Bob private" in page.text
    assert alice.get(master_url + "/state").status_code == 302
    master.post(master_url + "/serve-next", data=hidden_fields(page))
    assert "Currently serving" in alice.get(client_url + "/state").text
    master.post(master_url + "/done", data=hidden_fields(master.get(master_url + "/state")))
    assert "Your request is complete" in alice.get(client_url + "/state").text
    assert "Currently serving" in bob.get(client_url + "/state").text
    master.post(master_url + "/end", data=hidden_fields(master.get(master_url + "/master")))
    for browser in (alice, bob):
        ended = browser.get(client_url + "/state")
        assert "Session ended" in ended.text and "/leave" not in ended.text
    assert "Session ended" in master.get(master_url + "/state").text
    master.post(
        "/auth/logout", data={"csrf_token": csrf_token(master.get("/instructor/dashboard"))}
    )
    assert master.get(master_url + "/state").status_code == 302
    # Even an already connected, now logged-out master only ever receives empty notices.
    assert all(notices(socket) == 5 for socket in (alice_socket, bob_socket, master_socket))


def test_disconnect_exit_and_reconnect_are_read_only_and_resync(
    app, queue_session, live_browser, hidden_fields
):
    browser, socket = live_browser()
    url = f"/session/{queue_session[1]}"
    browser.post(url + "/join", data=hidden_fields(browser.get(url)))
    with app.app_context():
        identity = db.session.scalar(db.select(StudentIdentity))
        last_seen = identity.last_seen_at
        entry_id = db.session.scalar(db.select(QueueEntry.id))
    socket.disconnect()
    assert browser.get(url + "/exit").status_code == 200
    assert "live-updates.js" not in browser.get(url + "/exit").text
    with app.app_context():
        queue.begin_serving(*queue_session, entry_id)
    page = browser.get(url + "/state")
    socket.connect(
        auth={
            "view": "client",
            "public_code": queue_session[1],
            "csrf_token": hidden_fields(page)["csrf_token"],
        }
    )
    assert socket.is_connected() and "Currently serving" in browser.get(url + "/state").text
    with app.app_context():
        assert db.session.scalar(db.select(StudentIdentity.last_seen_at)) == last_seen
        assert db.session.get(QueueEntry, entry_id).status == "serving"


def test_invalid_browser_cookie_cannot_fetch_identity_state(app, queue_session, live_browser):
    browser, _ = live_browser()
    browser.delete_cookie("tan_browser", path="/session")
    assert browser.get(f"/session/{queue_session[1]}/state").status_code == 409
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(StudentIdentity)) == 0


def test_socket_extension_is_per_factory(app, queue_session, live_browser):
    _, socket = live_browser()
    other_app = create_app({"TESTING": True, "SECRET_KEY": "independent-app"})
    assert other_app.extensions["socketio"] is not app.extensions["socketio"]
    assert app.extensions["socketio"].async_mode == "threading"
    with app.app_context():
        queue.join(queue_session[1], student_identity.new_token())
    assert notices(socket) == 1
