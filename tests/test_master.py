from unittest.mock import patch
from uuid import uuid4
from xml.etree import ElementTree

import pytest
import qrcode

from app.auth.services import register_instructor
from app.extensions import db
from app.models import QueueEntry
from app.services import queue, sessions, student_identity


@pytest.fixture
def master_browser(app, queue_session):
    def browser(identity=None):
        client = app.test_client()
        with client.session_transaction() as state:
            state["_user_id"] = str(identity or queue_session[0])
            state["_fresh"] = True
        return client

    return browser


def enqueue(app, code, count=1):
    with app.app_context():
        return [
            queue.join(code, student_identity.new_token(), f"Name {index}").id
            for index in range(count)
        ]


def test_empty_waiting_serving_completed_and_ended_views(
    app, queue_session, master_browser, hidden_fields
):
    client = master_browser()
    base = f"/instructor/sessions/{queue_session[1]}"
    empty = client.get(base + "/master")
    assert empty.status_code == 200 and empty.headers["Cache-Control"] == "no-store"
    assert "No one currently serving" in empty.text and "Queue empty" in empty.text
    assert "Total waiting: 0" in empty.text
    assert ">Done</button>" not in empty.text and ">Serve next</button>" not in empty.text
    first, second = enqueue(app, queue_session[1], 2)
    waiting = client.get(base + "/master")
    assert "Total waiting: 2" in waiting.text and ">Serve next</button>" in waiting.text
    assert ">Done</button>" not in waiting.text
    assert hidden_fields(waiting)["entry_id"] == str(first)
    start = client.post(base + "/serve-next", data=hidden_fields(waiting))
    assert start.status_code == 303 and start.location == base + "/master"
    serving = client.get(start.location)
    assert "Total waiting: 1" in serving.text and ">Done</button>" in serving.text
    assert ">Serve next</button>" not in serving.text
    assert hidden_fields(serving)["entry_id"] == str(first)
    assert client.post(base + "/done", data=hidden_fields(serving)).status_code == 303
    last = client.get(base + "/master")
    assert hidden_fields(last)["entry_id"] == str(second)
    assert "Total waiting: 0" in last.text and "No one next" in last.text
    client.post(base + "/done", data=hidden_fields(last))
    assert "No one currently serving" in client.get(base + "/master").text
    client.post(base + "/end", data=hidden_fields(last))
    ended = client.get(base + "/master")
    assert "Session ended" in ended.text
    for action in ("/done", "/serve-next", "/qr.svg", "/end"):
        assert base + action not in ended.text
    assert client.post(base + "/done", data=hidden_fields(last)).status_code == 409


def test_master_truncates_and_escapes_names(app, queue_session, master_browser):
    entries = enqueue(app, queue_session[1], 7)
    with app.app_context():
        db.session.get(QueueEntry, entries[0]).display_name = "<script>alert(1)</script>"
        db.session.commit()
    response = master_browser().get(f"/instructor/sessions/{queue_session[1]}/master")
    assert "Showing 5 of 7 waiting, including Next Up" in response.text
    assert "Name 4" in response.text and "Name 5" not in response.text
    assert "<script>" not in response.text and "&lt;script&gt;" in response.text
    assert "tan_browser" not in response.text and "public_token_hash" not in response.text


def test_multiple_masters_and_replayed_forms_do_not_skip_students(
    app, queue_session, master_browser, hidden_fields
):
    first, second, third = enqueue(app, queue_session[1], 3)
    one, two = master_browser(), master_browser()
    base = f"/instructor/sessions/{queue_session[1]}"
    stale_start = hidden_fields(two.get(base + "/master"))
    one.post(base + "/serve-next", data=hidden_fields(one.get(base + "/master")))
    two.post(base + "/serve-next", data=stale_start)
    stale_done = hidden_fields(two.get(base + "/master"))
    one.post(base + "/done", data=hidden_fields(one.get(base + "/master")))
    replay = two.post(base + "/done", data=stale_done, follow_redirects=True)
    assert "already applied" in replay.text
    assert hidden_fields(replay)["entry_id"] == str(second)
    assert hidden_fields(one.get(base + "/master"))["entry_id"] == str(second)
    with app.app_context():
        assert db.session.get(QueueEntry, first).status == "completed"
        assert db.session.get(QueueEntry, third).status == "waiting"


@pytest.mark.parametrize("action", ["serve-next", "done"])
def test_advancement_requires_login_csrf_valid_form_and_owner(
    app, queue_session, master_browser, csrf_token, action
):
    entry_id = enqueue(app, queue_session[1])[0]
    url = f"/instructor/sessions/{queue_session[1]}/{action}"
    anonymous = app.test_client()
    token = csrf_token(anonymous.get("/auth/login"))
    response = anonymous.post(url, data={"csrf_token": token, "entry_id": str(entry_id)})
    assert response.status_code == 302 and "/auth/login" in response.location
    owner = master_browser()
    assert owner.get(url).status_code == 405
    assert owner.post(url, data={"entry_id": str(entry_id)}).status_code == 400
    token = csrf_token(owner.get("/instructor/dashboard"))
    for value in (None, "not-a-uuid"):
        assert owner.post(url, data={"csrf_token": token, "entry_id": value}).status_code == 400
    with app.app_context():
        other_id = register_instructor(
            "unauthorized-master@example.edu", "Other", "a long test password"
        ).id
    other = master_browser(other_id)
    token = csrf_token(other.get("/instructor/dashboard"))
    assert (
        other.post(
            url,
            data={
                "csrf_token": token,
                "entry_id": str(entry_id),
                "instructor_id": str(queue_session[0]),
            },
        ).status_code
        == 404
    )
    assert other.get(f"/instructor/sessions/{queue_session[1]}/qr.svg").status_code == 404
    token = csrf_token(owner.get("/instructor/dashboard"))
    assert (
        owner.post(
            f"/instructor/sessions/unknown/{action}",
            data={
                "csrf_token": token,
                "entry_id": str(uuid4()),
            },
        ).status_code
        == 404
    )
    with app.app_context():
        assert db.session.get(QueueEntry, entry_id).status == "waiting"


def test_qr_encodes_exact_public_url_and_is_only_for_owned_active_session(
    app, queue_session, master_browser
):
    client = master_browser()
    # Authenticate on the HTTPS origin too; cookies are intentionally host-scoped.
    with client.session_transaction(base_url="https://lab.example.edu") as state:
        state["_user_id"] = str(queue_session[0])
        state["_fresh"] = True
    base = f"/instructor/sessions/{queue_session[1]}"
    with patch("app.instructor.routes.qrcode.make", wraps=qrcode.make) as make:
        response = client.get(base + "/qr.svg", base_url="https://lab.example.edu")
    assert response.status_code == 200 and response.mimetype == "image/svg+xml"
    assert response.headers["Cache-Control"] == "no-store"
    expected_url = f"https://lab.example.edu/session/{queue_session[1]}"
    assert make.call_args.args == (expected_url,)
    svg = ElementTree.fromstring(response.data)
    assert svg.tag == "{http://www.w3.org/2000/svg}svg"
    assert svg.find("{http://www.w3.org/2000/svg}path").attrib["d"]
    assert svg.find("{http://www.w3.org/2000/svg}rect").attrib["fill"] == "white"
    page = client.get(base + "/master", base_url="https://lab.example.edu")
    assert expected_url in page.text
    assert app.test_client().get(f"/session/{queue_session[1]}").status_code == 200
    assert app.test_client().get(base + "/qr.svg").status_code == 302
    assert client.get("/instructor/sessions/missing/qr.svg").status_code == 404
    with app.app_context():
        sessions.end_session(*queue_session)
    assert client.get(base + "/qr.svg").status_code == 404
