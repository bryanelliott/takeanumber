from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from app.auth.services import register_instructor
from app.extensions import db
from app.models import Instructor

pytestmark = pytest.mark.usefixtures("auth_db")


@pytest.fixture
def instructor_id(app, signup_data):
    with app.app_context():
        instructor = register_instructor(
            signup_data["email"], signup_data["display_name"], signup_data["password"]
        )
        return instructor.id


def test_signup_normalizes_email_and_requires_login(app, client, signup_data, post_form):
    signup_data.update(email="  FACULTY@EXAMPLE.EDU  ", display_name=" Faculty Example ")
    response = post_form(client, "/auth/signup", signup_data)
    assert response.status_code == 302
    assert response.location == "/auth/login"
    assert client.get("/instructor/dashboard").status_code == 302
    with app.app_context():
        instructor = db.session.scalar(db.select(Instructor))
        assert instructor.email == "faculty@example.edu"
        assert instructor.display_name == "Faculty Example"
        assert instructor.password_hash != signup_data["password"]
        assert instructor.check_password(signup_data["password"])
        assert instructor.created_at.utcoffset().total_seconds() == 0


def test_case_variant_signup_is_duplicate(app, client, signup_data, post_form, instructor_id):
    signup_data["email"] = " FACULTY@EXAMPLE.EDU "
    response = post_form(client, "/auth/signup", signup_data)
    assert response.status_code == 409
    assert "Unable to create an account" in response.text
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Instructor)) == 1


def test_simultaneous_signup_is_unique(app, signup_data, post_form):
    def signup(_):
        with app.test_client() as browser:
            return post_form(browser, "/auth/signup", signup_data).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(signup, range(2))) == [302, 409]
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Instructor)) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"email": "not-an-email"},
        {"email": "name@localhost"},
        {"display_name": " \t\n "},
        {"display_name": "x" * 101},
        {"password": "short", "confirm_password": "short"},
        {"password": "x" * 129, "confirm_password": "x" * 129},
        {"confirm_password": "a different long password"},
        {"email": ""},
    ],
)
def test_invalid_signup_creates_no_account(app, client, signup_data, post_form, changes):
    signup_data.update(changes)
    response = post_form(client, "/auth/signup", signup_data)
    assert response.status_code == 400
    assert 'role="alert"' in response.text
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Instructor)) == 0


def test_login_persists_and_logout_clears_session(
    client, signup_data, post_form, csrf_token, instructor_id
):
    with client.session_transaction() as browser_session:
        browser_session["old_marker"] = True
    signup_data["email"] = " FACULTY@EXAMPLE.EDU "
    response = post_form(client, "/auth/login", signup_data)
    assert response.location == "/instructor/dashboard"
    with client.session_transaction() as browser_session:
        assert browser_session["_user_id"] == str(instructor_id)
        assert "old_marker" not in browser_session
        assert signup_data["password"] not in str(dict(browser_session))
    dashboard = client.get("/instructor/dashboard")
    assert dashboard.status_code == 200
    assert "Welcome, Faculty Example." in dashboard.text
    assert client.get("/instructor/dashboard").status_code == 200
    assert client.get("/auth/logout").status_code == 405
    assert client.post("/auth/logout").status_code == 400
    assert client.get("/instructor/dashboard").status_code == 200
    response = client.post("/auth/logout", data={"csrf_token": csrf_token(dashboard)})
    assert response.location == "/auth/login"
    assert client.get("/instructor/dashboard").status_code == 302


def test_dashboard_requires_authentication(client):
    response = client.get("/instructor/dashboard")
    assert response.status_code == 302
    assert response.location.startswith("/auth/login?next=")
    assert "Faculty Example" not in response.text
    assert client.get("/health").status_code == 200


def test_wrong_password_unknown_email_and_inactive_account_are_generic(
    app, client, signup_data, post_form, instructor_id
):
    wrong = {**signup_data, "password": "a wrong long password"}
    unknown = {**signup_data, "email": "unknown@example.edu"}
    for credentials in (wrong, unknown):
        response = post_form(client, "/auth/login", credentials)
        assert response.status_code == 401
        assert "Invalid email or password." in response.text
        assert client.get("/instructor/dashboard").status_code == 302
    with app.app_context():
        db.session.get(Instructor, instructor_id).is_active = False
        db.session.commit()
    response = post_form(client, "/auth/login", signup_data)
    assert response.status_code == 401
    assert "Invalid email or password." in response.text


def test_inactive_account_loses_existing_session(
    app, client, signup_data, post_form, instructor_id
):
    post_form(client, "/auth/login", signup_data)
    with app.app_context():
        db.session.get(Instructor, instructor_id).is_active = False
        db.session.commit()
    assert client.get("/instructor/dashboard").status_code == 302


@pytest.mark.parametrize("identity", ["not-a-uuid", str(uuid4())])
def test_stale_or_malformed_session_redirects(client, identity):
    with client.session_transaction() as browser_session:
        browser_session["_user_id"] = identity
    assert client.get("/instructor/dashboard").status_code == 302


@pytest.mark.parametrize("path", ["/auth/signup", "/auth/login", "/auth/logout"])
def test_missing_and_invalid_csrf_rejected(client, signup_data, path):
    assert client.post(path, data=signup_data).status_code == 400
    assert client.post(path, data={**signup_data, "csrf_token": "invalid"}).status_code == 400


def test_csrf_token_from_another_browser_is_rejected(app, client, signup_data, csrf_token):
    token = csrf_token(app.test_client().get("/auth/signup"))
    response = client.post("/auth/signup", data={**signup_data, "csrf_token": token})
    assert response.status_code == 400


@pytest.mark.parametrize("next_url", ["https://evil.example", "//evil.example", "/\\evil.example"])
def test_login_never_redirects_to_untrusted_next(
    client, signup_data, post_form, instructor_id, next_url
):
    response = post_form(client, "/auth/login?next=" + next_url, signup_data)
    assert response.location == "/instructor/dashboard"


def test_dashboard_is_scoped_to_current_account_and_escapes_names(
    app, client, signup_data, post_form, instructor_id
):
    with app.app_context():
        register_instructor("other@example.edu", "Other Instructor", signup_data["password"])
        db.session.get(Instructor, instructor_id).display_name = "<script>alert(1)</script>"
        db.session.commit()
    post_form(client, "/auth/login", signup_data)
    response = client.get("/instructor/dashboard")
    assert "Other Instructor" not in response.text
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_password_is_not_echoed_on_form_error(client, signup_data, post_form):
    signup_data["confirm_password"] = "different confirmation"
    response = post_form(client, "/auth/signup", signup_data)
    assert signup_data["password"] not in response.text
    assert signup_data["confirm_password"] not in response.text
