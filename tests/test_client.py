from unittest.mock import patch

import pytest

from app.extensions import db
from app.models import QueueEntry, StudentIdentity
from app.queue import browser
from app.services import sessions, student_identity


def test_public_join_refresh_leave_and_rejoin(app, client, queue_session, hidden_fields):
    path = f"/session/{queue_session[1]}"
    page = client.get(path)
    assert page.status_code == 200 and "Take A Number" in page.text
    assert "Instructor login" not in page.text
    fields = hidden_fields(page)
    assert client.post(path + "/join", data=fields).status_code == 303
    active = client.get(path)
    assert 'data-client-status="waiting"' in active.text and "People ahead: 0" in active.text
    assert client.post(path + "/join", data=fields).status_code == 303
    refreshed = client.get(path)
    assert hidden_fields(active)["entry_id"] == hidden_fields(refreshed)["entry_id"]
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(QueueEntry)) == 1
        entry = db.session.scalar(db.select(QueueEntry))
        assert entry.display_name is None
    assert client.post(path + "/leave", data=hidden_fields(active)).status_code == 303
    left = client.get(path)
    assert "You left the queue" in left.text
    assert client.post(path + "/join", data=hidden_fields(left)).status_code == 303
    assert client.post(path + "/leave", data=hidden_fields(active)).status_code == 303
    assert 'data-client-status="waiting"' in client.get(path).text
    with app.app_context():
        entries = db.session.scalars(db.select(QueueEntry).order_by(QueueEntry.queue_number)).all()
        assert [(entry.queue_number, entry.status) for entry in entries] == [
            (1, "left"),
            (2, "waiting"),
        ]


def test_exit_is_read_only_and_return_restores_request(app, client, queue_session, hidden_fields):
    path = f"/session/{queue_session[1]}"
    client.post(path + "/join", data=hidden_fields(client.get(path)))
    with app.app_context():
        entry = db.session.scalar(db.select(QueueEntry))
        before = entry.id, entry.status, entry.joined_at, entry.updated_at, entry.left_at
        identity = db.session.scalar(db.select(StudentIdentity))
        last_seen = identity.last_seen_at
    exited = client.get(path + "/exit")
    assert exited.status_code == 200 and "Return to session" in exited.text
    assert 'data-client-status="waiting"' in client.get(path).text
    with app.app_context():
        entry = db.session.scalar(db.select(QueueEntry))
        assert (entry.id, entry.status, entry.joined_at, entry.updated_at, entry.left_at) == before
        assert db.session.scalar(db.select(StudentIdentity)).last_seen_at == last_seen


def test_browser_cookie_is_separate_persistent_httponly_and_hash_not_exposed(
    app, client, queue_session, hidden_fields
):
    path = f"/session/{queue_session[1]}"
    response = client.get(path)
    cookie_header = next(
        value
        for value in response.headers.getlist("Set-Cookie")
        if value.startswith(browser.COOKIE_NAME + "=")
    )
    assert "HttpOnly" in cookie_header and "SameSite=Lax" in cookie_header
    assert "Path=/session" in cookie_header and "Max-Age=15552000" in cookie_header
    cookie = client.get_cookie(browser.COOKIE_NAME, path=browser.COOKIE_PATH)
    with app.app_context():
        token = browser.serializer().loads(cookie.value)
        digest = student_identity.token_hash(token)
    assert token not in response.text and digest not in response.text
    client.post(path + "/join", data=hidden_fields(response))
    # A fresh browser process with the same persisted identity but no Flask login/CSRF session.
    reopened = app.test_client()
    reopened.set_cookie(browser.COOKIE_NAME, cookie.value, path=browser.COOKIE_PATH)
    restored = reopened.get(path)
    assert 'data-client-status="waiting"' in restored.text
    assert "no-store" in restored.headers["Cache-Control"]
    assert restored.headers["Referrer-Policy"] == "same-origin"


def test_https_cookie_flag(app, client, queue_session):
    app.config["SESSION_COOKIE_SECURE"] = True
    response = client.get(f"/session/{queue_session[1]}", base_url="https://localhost")
    header = next(
        value
        for value in response.headers.getlist("Set-Cookie")
        if value.startswith(browser.COOKIE_NAME + "=")
    )
    assert "Secure" in header


def test_https_join_and_leave_with_same_origin_referrer(
    app, client, queue_session, hidden_fields
):
    app.config["SESSION_COOKIE_SECURE"] = True
    path = f"/session/{queue_session[1]}"
    base_url = "https://localhost"
    # A QR/direct navigation has no referrer; subsequent forms use the page policy.
    page = client.get(path, base_url=base_url)
    assert page.status_code == 200
    assert page.headers["Referrer-Policy"] == "same-origin"
    headers = {"Referer": base_url + path}
    joined = client.post(
        path + "/join", data=hidden_fields(page), base_url=base_url, headers=headers
    )
    assert joined.status_code == 303
    active = client.get(path, base_url=base_url)
    assert 'data-client-status="waiting"' in active.text
    left = client.post(
        path + "/leave", data=hidden_fields(active), base_url=base_url, headers=headers
    )
    assert left.status_code == 303
    assert "You left the queue" in client.get(path, base_url=base_url).text


@pytest.mark.parametrize("action", ["join", "leave"])
@pytest.mark.parametrize(
    "invalid", ["missing_referrer", "foreign_referrer", "missing_token", "bad_token"]
)
def test_https_student_forms_retain_csrf_checks(
    app, client, queue_session, hidden_fields, action, invalid
):
    path = f"/session/{queue_session[1]}"
    base_url = "https://localhost"
    headers = {"Referer": base_url + path}
    page = client.get(path, base_url=base_url)
    if action == "leave":
        assert client.post(
            path + "/join", data=hidden_fields(page), base_url=base_url, headers=headers
        ).status_code == 303
        page = client.get(path, base_url=base_url)
    fields = hidden_fields(page)
    if invalid == "missing_referrer":
        headers = {}
    elif invalid == "foreign_referrer":
        headers = {"Referer": "https://other.example/session"}
    elif invalid == "missing_token":
        fields.pop("csrf_token")
    else:
        fields["csrf_token"] = "invalid"
    response = client.post(
        path + "/" + action, data=fields, base_url=base_url, headers=headers
    )
    assert response.status_code == 400
    with app.app_context():
        entries = db.session.scalars(db.select(QueueEntry)).all()
        assert [entry.status for entry in entries] == (["waiting"] if action == "leave" else [])


@pytest.mark.parametrize("cookie_value", [None, "tampered", "x" * 300])
def test_missing_or_invalid_cookie_cannot_join(
    app, client, queue_session, hidden_fields, cookie_value
):
    path = f"/session/{queue_session[1]}"
    fields = hidden_fields(client.get(path))
    client.delete_cookie(browser.COOKIE_NAME, path=browser.COOKIE_PATH)
    if cookie_value is not None:
        client.set_cookie(browser.COOKIE_NAME, cookie_value, path=browser.COOKIE_PATH)
    for _ in range(2):
        response = client.post(path + "/join", data=fields)
        assert response.status_code == 409 and "Allow cookies" in response.text
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(QueueEntry)) == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(StudentIdentity)) == 0


def test_changed_cookie_cannot_submit_old_form(app, client, queue_session, hidden_fields):
    path = f"/session/{queue_session[1]}"
    fields = hidden_fields(client.get(path))
    with app.app_context():
        replacement = browser.serializer().dumps(student_identity.new_token())
    client.set_cookie(browser.COOKIE_NAME, replacement, path=browser.COOKIE_PATH)
    assert client.post(path + "/join", data=fields).status_code == 409
    assert client.post(path + "/join", data=hidden_fields(client.get(path))).status_code == 303


def test_expired_cookie_does_not_mutate_queue_and_get_renews_identity(
    app, client, queue_session, hidden_fields
):
    path = f"/session/{queue_session[1]}"
    fields = hidden_fields(client.get(path))
    with (
        app.app_context(),
        patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=1),
    ):
        expired = browser.serializer().dumps(student_identity.new_token())
    client.set_cookie(browser.COOKIE_NAME, expired, path=browser.COOKIE_PATH)
    assert client.post(path + "/join", data=fields).status_code == 409
    reopened = client.get(path)
    assert client.get_cookie(browser.COOKIE_NAME, path=browser.COOKIE_PATH).value != expired
    assert client.post(path + "/join", data=hidden_fields(reopened)).status_code == 303


def test_cleared_cookie_does_not_claim_recovery_or_merge_by_name(
    app, client, queue_session, hidden_fields
):
    path = f"/session/{queue_session[1]}"
    client.post(
        path + "/join", data={**hidden_fields(client.get(path)), "display_name": "Same name"}
    )
    client.delete_cookie(browser.COOKIE_NAME, path=browser.COOKIE_PATH)
    page = client.get(path)
    assert 'data-client-status="not_joined"' in page.text
    client.post(path + "/join", data={**hidden_fields(page), "display_name": "Same name"})
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(StudentIdentity)) == 2
        assert db.session.scalar(db.select(db.func.count()).select_from(QueueEntry)) == 2


def test_no_other_browser_data_or_identity_override(app, client, queue_session, hidden_fields):
    path = f"/session/{queue_session[1]}"
    client.post(
        path + "/join", data={**hidden_fields(client.get(path)), "display_name": "Private Name"}
    )
    first_fields = hidden_fields(client.get(path))
    other = app.test_client()
    other_page = other.get(path)
    assert "Private Name" not in other_page.text
    other.post(
        path + "/join",
        data={
            **hidden_fields(other_page),
            "display_name": "Second Name",
            "student_identity_id": "forged",
            "queue_number": "1",
            "status": "serving",
        },
    )
    assert "Private Name" not in other.get(path).text
    assert "People ahead: 1" in other.get(path).text
    stolen_target = {**hidden_fields(other.get(path)), "entry_id": first_fields["entry_id"]}
    assert other.post(path + "/leave", data=stolen_target).status_code == 404
    assert 'data-client-status="waiting"' in client.get(path).text


def test_optional_name_validation_and_escaping(client, queue_session, hidden_fields):
    path = f"/session/{queue_session[1]}"
    fields = hidden_fields(client.get(path))
    assert (
        client.post(path + "/join", data={**fields, "display_name": "x" * 101}).status_code == 400
    )
    name = "<script>alert(1)</script>"
    assert client.post(path + "/join", data={**fields, "display_name": name}).status_code == 303
    response = client.get(path)
    assert name not in response.text and "&lt;script&gt;" in response.text


def test_no_location_fingerprinting_or_extra_personal_fields(
    app, client, queue_session, hidden_fields
):
    path = f"/session/{queue_session[1]}"
    response = client.get(path, headers={"User-Agent": "arbitrary-browser", "X-Forwarded-For": "x"})
    assert "geolocation" not in response.text and "navigator." not in response.text
    client.post(
        path + "/join",
        data={
            **hidden_fields(response),
            "seat": "DO-NOT-STORE",
            "latitude": "DO-NOT-STORE",
            "workstation": "DO-NOT-STORE",
        },
    )
    with app.app_context():
        identity = db.session.scalar(db.select(StudentIdentity))
        entry = db.session.scalar(db.select(QueueEntry))
        assert set(StudentIdentity.__table__.columns.keys()) == {
            "id",
            "public_token_hash",
            "first_seen_at",
            "last_seen_at",
            "created_at",
        }
        assert "DO-NOT-STORE" not in str(entry.__dict__)
        assert "arbitrary-browser" not in str(identity.__dict__)
    assert "DO-NOT-STORE" not in client.get(path).text


def test_student_endpoints_require_csrf_and_mutations_are_post_only(client, queue_session):
    path = f"/session/{queue_session[1]}"
    client.get(path)
    for suffix in ("/join", "/leave"):
        assert client.get(path + suffix).status_code == 405
        assert client.post(path + suffix).status_code == 400
        assert client.post(path + suffix, data={"csrf_token": "bad"}).status_code == 400


def test_ended_session_has_no_join_or_leave_controls(app, client, queue_session, hidden_fields):
    path = f"/session/{queue_session[1]}"
    fields = hidden_fields(client.get(path))
    client.post(path + "/join", data=fields)
    leave_fields = hidden_fields(client.get(path))
    with app.app_context():
        sessions.end_session(*queue_session)
    assert client.post(path + "/join", data=fields).status_code == 409
    assert client.post(path + "/leave", data=leave_fields).status_code == 409
    response = client.get(path)
    assert "Session ended" in response.text
    assert "<form" not in response.text and "People ahead:" not in response.text
    assert "Estimated wait:" not in response.text


def test_unknown_session_is_404_without_creating_identity(app, client, queue_session):
    assert client.get("/session/unknown").status_code == 404
    assert client.get("/session/unknown/exit").status_code == 404
    assert client.get_cookie(browser.COOKIE_NAME, path=browser.COOKIE_PATH) is None
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(StudentIdentity)) == 0


def test_student_cookie_cannot_authorize_instructor_routes(client, queue_session, hidden_fields):
    path = f"/session/{queue_session[1]}"
    fields = hidden_fields(client.get(path))
    client.post(path + "/join", data=fields)
    master = client.get(f"/instructor/sessions/{queue_session[1]}/master")
    assert master.status_code == 302 and "/auth/login" in master.location


def test_flask_session_reset_does_not_lose_queue_identity(client, queue_session, hidden_fields):
    path = f"/session/{queue_session[1]}"
    client.post(path + "/join", data=hidden_fields(client.get(path)))
    with client.session_transaction() as state:
        state.clear()
    assert 'data-client-status="waiting"' in client.get(path).text
