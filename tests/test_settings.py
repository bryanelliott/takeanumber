from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.auth.services import register_instructor
from app.extensions import db
from app.models import InstructorSetting
from app.services import queue, sessions, settings, student_identity


@pytest.fixture
def owner_browser(app, queue_session):
    browser = app.test_client()
    with browser.session_transaction() as state:
        state["_user_id"] = str(queue_session[0])
        state["_fresh"] = True
    return browser


def test_signup_creates_one_default_settings_record(app, queue_session):
    with app.app_context():
        row = db.session.scalar(db.select(InstructorSetting))
        assert row.instructor_id == queue_session[0]
        assert row.id and row.created_at.tzinfo and row.updated_at.tzinfo
        assert settings.get_preferences(queue_session[0]) == settings.AlertPreferences()
        assert db.session.scalar(db.select(db.func.count()).select_from(InstructorSetting)) == 1


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"advance_warning_count": 0},
        {"advance_warning_count": 4},
        {"advance_warning_count": None},
        {"sound_alert_enabled": None},
        {"instructor_id": uuid4()},
    ],
)
def test_database_enforces_owner_uniqueness_range_and_required_values(app, queue_session, values):
    with app.app_context():
        # Empty values exercise the duplicate-owner constraint; other cases isolate constraints.
        if values and "instructor_id" not in values:
            db.session.execute(db.delete(InstructorSetting))
            db.session.commit()
        data = {"id": uuid4(), "instructor_id": queue_session[0], **values}
        with pytest.raises(IntegrityError):
            db.session.execute(db.insert(InstructorSetting).values(**data))
            db.session.commit()
        db.session.rollback()


def test_settings_require_login_and_csrf(client, owner_browser, csrf_token):
    response = client.get("/instructor/settings")
    assert response.status_code == 302 and "/auth/login" in response.location
    assert (
        owner_browser.post("/instructor/settings", data={"advance_warning_count": "2"}).status_code
        == 400
    )
    token = csrf_token(client.get("/auth/login"))
    response = client.post(
        "/instructor/settings", data={"csrf_token": token, "advance_warning_count": "2"}
    )
    assert response.status_code == 302 and "/auth/login" in response.location


def test_save_all_toggles_and_ignore_forged_owner(app, queue_session, owner_browser, post_form):
    with app.app_context():
        other = register_instructor(
            "other-settings@example.edu", "Other", "a long test password"
        ).id
        original = db.session.scalar(
            db.select(InstructorSetting).where(InstructorSetting.instructor_id == queue_session[0])
        )
        row_id, created_at = original.id, original.created_at
    response = post_form(
        owner_browser,
        "/instructor/settings",
        {
            "advance_warning_count": "3",
            "instructor_id": str(other),
            "id": str(uuid4()),
        },
    )
    assert response.status_code == 303
    with app.app_context():
        prefs = settings.get_preferences(queue_session[0])
        assert prefs == settings.AlertPreferences(False, False, False, False, False, 3)
        assert settings.get_preferences(other) == settings.AlertPreferences()
        row = db.session.get(InstructorSetting, row_id)
        assert row.created_at == created_at and row.updated_at >= created_at
        assert db.session.scalar(db.select(db.func.count()).select_from(InstructorSetting)) == 2
    response = post_form(
        owner_browser,
        "/instructor/settings",
        {
            **{
                key: "y"
                for key in asdict(settings.AlertPreferences())
                if key != "advance_warning_count"
            },
            "advance_warning_count": "1",
        },
    )
    assert response.status_code == 303
    with app.app_context():
        assert settings.get_preferences(queue_session[0]) == settings.AlertPreferences()
    page = owner_browser.get("/instructor/settings")
    assert 'href="/instructor/settings"' in page.text and 'value="1"' in page.text
    assert "no-store" in page.headers["Cache-Control"]
    assert "Web Push is not available" in page.text
    assert owner_browser.get(f"/instructor/{other}/settings").status_code == 404


@pytest.mark.parametrize("distance", ["0", "4", "-1", "1.5", "abc", ""])
def test_invalid_distance_does_not_save(app, queue_session, owner_browser, post_form, distance):
    response = post_form(owner_browser, "/instructor/settings", {"advance_warning_count": distance})
    assert response.status_code == 400 and 'role="alert"' in response.text
    with app.app_context():
        assert settings.get_preferences(queue_session[0]) == settings.AlertPreferences()


@pytest.mark.parametrize("count", [1, 2, 3])
def test_warning_distance_counts_waiting_requests_and_preserves_next_up(app, queue_session, count):
    with app.app_context():
        settings.save_preferences(
            queue_session[0], settings.AlertPreferences(advance_warning_count=count)
        )
        tokens = [student_identity.new_token() for _ in range(5)]
        ids = [queue.join(queue_session[1], token).id for token in tokens]
        queue.leave(queue_session[1], tokens[1], ids[1])  # number gap must not count
        queue.begin_serving(*queue_session, ids[0])
        states = [queue.client_state(queue_session[1], token) for token in tokens]
        assert states[0].alert_state == "serving"
        assert states[1].alert_state is None
        assert states[2].alert_state == "next_up"
        for rank, state in enumerate(states[2:], start=1):
            expected = "next_up" if rank == 1 else "advance_warning" if rank <= count else None
            assert state.alert_state == expected
        queue.complete_current(*queue_session, ids[0])
        assert queue.client_state(queue_session[1], tokens[0]).alert_state is None
        assert queue.client_state(queue_session[1], tokens[2]).alert_state == "serving"
        sessions.end_session(*queue_session)
        assert all(
            queue.client_state(queue_session[1], token).alert_state is None for token in tokens
        )


def test_alert_preferences_apply_to_own_session_without_hiding_status(
    app, queue_session, hidden_fields
):
    browser = app.test_client()
    url = f"/session/{queue_session[1]}"
    browser.post(url + "/join", data=hidden_fields(browser.get(url)))
    with app.app_context():
        settings.save_preferences(
            queue_session[0], settings.AlertPreferences(False, False, False, False, False, 3)
        )
        other = register_instructor("separate@example.edu", "Separate", "a long test password").id
        other_code = sessions.start_session(other).public_code
        token = student_identity.new_token()
        queue.join(other_code, token)
        assert queue.client_state(other_code, token).preferences == settings.AlertPreferences()
    page = browser.get(url + "/state")
    assert "You're next" in page.text and "/leave" in page.text
    assert 'class="student-alert' not in page.text
    for attribute in ("alert-enabled", "visual-enabled", "sound-allowed", "vibration-allowed"):
        assert f'data-{attribute}="false"' in page.text
    entry_id = hidden_fields(page)["entry_id"]
    with app.app_context():
        queue.begin_serving(*queue_session, entry_id)
    page = browser.get(url + "/state")
    assert "Currently serving" in page.text and 'data-alert-enabled="false"' in page.text


def test_visual_toggle_does_not_disable_sound_or_status(app, queue_session, hidden_fields):
    browser = app.test_client()
    url = f"/session/{queue_session[1]}"
    browser.post(url + "/join", data=hidden_fields(browser.get(url)))
    with app.app_context():
        settings.save_preferences(
            queue_session[0], settings.AlertPreferences(visual_alert_enabled=False)
        )
    page = browser.get(url + "/state")
    assert "You're next" in page.text and 'class="student-alert' not in page.text
    assert 'data-alert-enabled="true"' in page.text and 'data-sound-allowed="true"' in page.text


@pytest.mark.parametrize("next_enabled,serving_enabled", [(False, True), (True, False)])
def test_event_toggles_are_independent(app, queue_session, next_enabled, serving_enabled):
    with app.app_context():
        settings.save_preferences(
            queue_session[0],
            settings.AlertPreferences(
                alert_next_enabled=next_enabled,
                alert_serving_enabled=serving_enabled,
                advance_warning_count=3,
            ),
        )
        token = student_identity.new_token()
        entry_id = queue.join(queue_session[1], token).id
        state = queue.client_state(queue_session[1], token)
        assert state.preferences.permits(state.alert_state) is next_enabled
        assert state.preferences.permits("advance_warning") is next_enabled
        queue.begin_serving(*queue_session, entry_id)
        state = queue.client_state(queue_session[1], token)
        assert state.preferences.permits(state.alert_state) is serving_enabled


def test_save_notifies_only_owned_active_session_after_commit(app, queue_session, csrf_token):
    browser = app.test_client()
    page = browser.get(f"/session/{queue_session[1]}")
    socket = app.extensions["socketio"].test_client(
        app,
        flask_test_client=browser,
        auth={
            "view": "client",
            "public_code": queue_session[1],
            "csrf_token": csrf_token(page),
        },
    )
    try:
        with app.app_context():
            with patch.object(db.session, "commit", side_effect=RuntimeError("rollback")):
                with pytest.raises(RuntimeError):
                    settings.save_preferences(
                        queue_session[0], settings.AlertPreferences(sound_alert_enabled=False)
                    )
            assert settings.get_preferences(queue_session[0]).sound_alert_enabled
            assert socket.get_received() == []
            settings.save_preferences(
                queue_session[0], settings.AlertPreferences(sound_alert_enabled=False)
            )
            assert not settings.get_preferences(queue_session[0]).sound_alert_enabled
            assert socket.get_received() == [
                {"name": "queue_changed", "args": [{}], "namespace": "/"}
            ]
            other = register_instructor("notice@example.edu", "Other", "a long test password").id
            sessions.start_session(other)
            settings.save_preferences(other, settings.AlertPreferences())
            assert socket.get_received() == []
    finally:
        socket.disconnect()


def test_concurrent_first_saves_create_one_complete_record(app, queue_session):
    with app.app_context():
        db.session.execute(db.delete(InstructorSetting))
        db.session.commit()
        assert settings.get_preferences(queue_session[0]) == settings.AlertPreferences()
    barrier = Barrier(2)
    options = [
        settings.AlertPreferences(advance_warning_count=2),
        settings.AlertPreferences(sound_alert_enabled=False),
    ]

    def save(prefs):
        with app.app_context():
            db.session.execute(db.text("SET LOCAL lock_timeout = '5s'"))
            barrier.wait(timeout=5)
            settings.save_preferences(queue_session[0], prefs)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(save, options))
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(InstructorSetting)) == 1
        assert settings.get_preferences(queue_session[0]) in options
