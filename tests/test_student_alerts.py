from unittest.mock import patch

import pytest

from app.auth.services import register_instructor
from app.extensions import db
from app.services import queue, sessions, student_identity


def test_next_up_is_first_waiting_not_simply_one_person_ahead(app, queue_session):
    tokens = [student_identity.new_token() for _ in range(3)]
    with app.app_context():
        entries = [queue.join(queue_session[1], token).id for token in tokens]
        first, second, third = [queue.client_state(queue_session[1], token) for token in tokens]
        assert first.status == "waiting" and first.alert_state == "next_up"
        assert second.people_ahead == 1 and second.alert_state is None
        assert third.people_ahead == 2 and third.alert_state is None
        queue.begin_serving(*queue_session, entries[0])
        first, second, third = [queue.client_state(queue_session[1], token) for token in tokens]
        assert first.status == "serving" and first.alert_state == "serving"
        assert second.people_ahead == 1 and second.alert_state == "next_up"
        assert third.alert_state is None
        queue.complete_current(*queue_session, entries[0])
        assert queue.client_state(queue_session[1], tokens[0]).alert_state is None
        assert queue.client_state(queue_session[1], tokens[1]).alert_state == "serving"
        assert queue.client_state(queue_session[1], tokens[2]).alert_state == "next_up"


def test_leave_gaps_rejoin_and_end_derive_correct_alerts(app, queue_session):
    tokens = [student_identity.new_token() for _ in range(3)]
    with app.app_context():
        assert queue.client_state(queue_session[1], tokens[0]).alert_state is None
        entries = [queue.join(queue_session[1], token).id for token in tokens]
        queue.leave(queue_session[1], tokens[0], entries[0])
        assert queue.client_state(queue_session[1], tokens[0]).alert_state is None
        assert queue.client_state(queue_session[1], tokens[1]).alert_state == "next_up"
        new_entry = queue.join(queue_session[1], tokens[0]).id
        assert new_entry != entries[0]
        assert queue.client_state(queue_session[1], tokens[0]).alert_state is None
        queue.begin_serving(*queue_session, entries[1])
        queue.leave(queue_session[1], tokens[1], entries[1])
        assert queue.client_state(queue_session[1], tokens[2]).alert_state == "next_up"
        sessions.end_session(*queue_session)
        assert all(
            queue.client_state(queue_session[1], token).alert_state is None for token in tokens
        )


def test_alert_selection_is_scoped_to_the_session(app, queue_session):
    token = student_identity.new_token()
    with app.app_context():
        queue.join(queue_session[1], token)
        other = register_instructor("alerts@example.edu", "Other", "a long test password")
        other_code = sessions.start_session(other.id).public_code
        first = queue.join(other_code, student_identity.new_token()).id
        queue.join(other_code, token)
        assert queue.client_state(queue_session[1], token).alert_state == "next_up"
        assert queue.client_state(other_code, token).alert_state is None
        queue.begin_serving(other.id, other_code, first)
        assert queue.client_state(other_code, token).alert_state == "next_up"
        assert queue.client_state(queue_session[1], token).alert_state == "next_up"


def test_socket_notice_only_triggers_private_authoritative_alert_read(
    app, queue_session, hidden_fields, csrf_token
):
    browser = app.test_client()
    url = f"/session/{queue_session[1]}"
    with app.app_context():
        first = queue.join(queue_session[1], student_identity.new_token(), "Private other name").id
    browser.post(url + "/join", data=hidden_fields(browser.get(url)))
    page = browser.get(url)
    assert 'data-alert-state=""' in page.text
    socket = app.extensions["socketio"].test_client(
        app,
        flask_test_client=browser,
        auth={"view": "client", "public_code": queue_session[1], "csrf_token": csrf_token(page)},
    )
    try:
        with app.app_context():
            # A failed transition produces neither a new state nor a notice.
            with patch.object(db.session, "commit", side_effect=RuntimeError("rollback")):
                with pytest.raises(RuntimeError):
                    queue.begin_serving(*queue_session, first)
        assert socket.get_received() == []
        assert 'data-alert-state=""' in browser.get(url + "/state").text
        with app.app_context():
            queue.begin_serving(*queue_session, first)
        assert socket.get_received() == [{"name": "queue_changed", "args": [{}], "namespace": "/"}]
        next_up = browser.get(url + "/state")
        assert 'data-alert-state="next_up"' in next_up.text
        assert "You're next" in next_up.text and "Private other name" not in next_up.text
        with app.app_context():
            queue.complete_current(*queue_session, first)
        assert socket.get_received() == [{"name": "queue_changed", "args": [{}], "namespace": "/"}]
        serving = browser.get(url + "/state")
        assert 'data-alert-state="serving"' in serving.text and "It's your turn" in serving.text
        with app.app_context():
            sessions.end_session(*queue_session)
        ended = browser.get(url + "/state")
        assert 'data-alert-state=""' in ended.text and "It's your turn" not in ended.text
        assert "You're next" not in ended.text
    finally:
        socket.disconnect()


def test_visual_state_and_optional_controls_are_accessible_without_browser_apis(
    app, queue_session, hidden_fields
):
    browser = app.test_client()
    url = f"/session/{queue_session[1]}"
    browser.post(url + "/join", data=hidden_fields(browser.get(url)))
    page = browser.get(url)
    assert "You're next" in page.text and 'aria-labelledby="student-alert-heading"' in page.text
    assert 'aria-live="polite"' in page.text and 'aria-atomic="true"' in page.text
    assert "Enable and test sound" in page.text and "Enable and test vibration" in page.text
    assert "animation: none" in page.text and "transition: none" in page.text
    assert "/leave" in page.text and "Exit" in page.text
    exit_page = browser.get(url + "/exit")
    assert "student-alerts.js" not in exit_page.text
    assert "student-alert-controls" not in exit_page.text
