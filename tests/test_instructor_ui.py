"""Presentation checks alongside existing auth, CSRF, ownership and settings tests."""

from html.parser import HTMLParser

import pytest

from app.services import sessions, settings


class Page(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.tags = []
        self.feed(markup)

    def handle_starttag(self, tag, attributes):
        self.tags.append((tag, dict(attributes)))

    def find(self, tag):
        return [attributes for name, attributes in self.tags if name == tag]

    def by_id(self, identity):
        return next(attributes for _, attributes in self.tags if attributes.get("id") == identity)


@pytest.mark.parametrize("path", ["/auth/login", "/auth/signup"])
def test_auth_cards_have_labeled_required_fields_and_local_assets(client, path):
    response = client.get(path)
    assert response.status_code == 200
    page = Page(response.text)
    assert len(page.find("h1")) == 1
    assert page.by_id("auth-heading")
    links = [link["href"] for link in page.find("a")]
    assert "/auth/login" in links and "/auth/signup" in links and "/" in links
    assert "/instructor/settings" not in links
    assert "reset" not in response.text.lower()
    labels = {label["for"] for label in page.find("label")}
    fields = {item["name"]: item for item in page.find("input") if item["type"] != "hidden"}
    assert set(fields) == (
        {"email", "password"} if path.endswith("login")
        else {"email", "display_name", "password", "confirm_password"}
    )
    for name, attributes in fields.items():
        assert attributes["id"] in labels and "required" in attributes
        assert attributes["aria-invalid"] == "false"
        for reference in attributes["aria-describedby"].split():
            assert page.by_id(reference)
        if "password" in name:
            assert attributes["type"] == "password" and not attributes.get("value")
            assert attributes["autocomplete"] == (
                "current-password" if path.endswith("login") else "new-password"
            )
    assert fields["email"]["autocomplete"] == "username"
    for button in page.find("button"):
        if "data-password-toggle" in button:
            assert button["type"] == "button" and "hidden" in button
            assert button["aria-controls"] in labels
    for asset in ("css/instructor.css", "instructor-forms.js"):
        assert f"/static/{asset}" in response.text
        assert client.get(f"/static/{asset}").status_code == 200


def test_signup_feedback_preserves_only_non_password_fields(client, signup_data, post_form):
    response = post_form(client, "/auth/signup", {
        **signup_data, "display_name": "Teacher <script>name</script>",
        "confirm_password": "different password confirmation",
    })
    assert response.status_code == 400
    page = Page(response.text)
    assert page.by_id("display_name")["value"] == "Teacher <script>name</script>"
    assert "Teacher <script>name</script>" not in response.text
    assert page.by_id("email")["value"] == signup_data["email"]
    assert page.by_id("confirm_password")["aria-invalid"] == "true"
    assert not page.by_id("password").get("value")
    assert not page.by_id("confirm_password").get("value")
    assert "15–128 characters. Spaces are allowed." in response.text
    assert 'role="alert"' in response.text


def test_settings_groups_save_feedback_and_dashboard_navigation(
    app, client, queue_session, post_form
):
    with client.session_transaction() as state:
        state["_user_id"] = str(queue_session[0])
        state["_fresh"] = True
    response = client.get("/instructor/settings")
    page = Page(response.text)
    assert page.by_id("timing-heading") and page.by_id("methods-heading")
    assert len([form for form in page.find("form") if "data-submit-feedback" in form]) == 1
    checkboxes = [item for item in page.find("input") if item.get("type") == "checkbox"]
    assert len(checkboxes) == 5 and all("checked" in item for item in checkboxes)
    for item in checkboxes:
        assert page.by_id(item["aria-labelledby"])
        for reference in item["aria-describedby"].split():
            assert page.by_id(reference)
    assert any(link.get("aria-current") == "page" and link["href"] == "/instructor/settings"
               for link in page.find("a"))
    invalid = post_form(client, "/instructor/settings", {
        "advance_warning_count": "4", "sound_alert_enabled": "y",
    })
    assert invalid.status_code == 400
    invalid_page = Page(invalid.text)
    assert invalid_page.by_id("advance_warning_count")["aria-invalid"] == "true"
    assert "checked" in invalid_page.by_id("sound_alert_enabled")
    assert "checked" not in invalid_page.by_id("visual_alert_enabled")
    with app.app_context():
        assert settings.get_preferences(queue_session[0]) == settings.AlertPreferences()
    saved = post_form(client, "/instructor/settings", {
        "advance_warning_count": "2", "sound_alert_enabled": "y",
    })
    assert saved.status_code == 303
    saved_page = client.get(saved.location)
    assert "Settings saved. Active student views will update automatically." in saved_page.text
    assert 'role="status"' in saved_page.text
    assert "checked" in Page(saved_page.text).by_id("sound_alert_enabled")
    with app.app_context():
        assert settings.get_preferences(queue_session[0]).advance_warning_count == 2
    dashboard = client.get("/instructor/dashboard")
    assert f'/instructor/sessions/{queue_session[1]}/master' in dashboard.text
    assert "Start help session" not in dashboard.text
    assert 'action="/auth/logout" method="post"' in dashboard.text
    with app.app_context():
        sessions.end_session(*queue_session)
    empty = client.get("/instructor/dashboard")
    assert 'action="/instructor/sessions" method="post"' in empty.text
    assert "No active help session" in empty.text
    assert "Open Master View" not in empty.text


def test_throttled_page_has_recovery_link_without_changing_retry_policy(app, client):
    app.extensions["auth_rate_limiter"].limit = 0
    response = client.post("/auth/login")
    assert response.status_code == 429 and int(response.headers["Retry-After"]) > 0
    assert "Please try again later" in response.text
    assert 'class="alert alert--warning"' in response.text
    assert 'href="/auth/login"' in response.text
