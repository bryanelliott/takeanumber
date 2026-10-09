"""Public entry point, shared UI semantics and existing authentication boundaries."""

from html.parser import HTMLParser
from unittest.mock import patch

import pytest
from flask import url_for

from app.extensions import db


class Elements(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.tags = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def find(self, tag):
        return [attrs for name, attrs in self.tags if name == tag]


def test_landing_is_public_and_does_not_query_database(app, client):
    with app.app_context(), patch.object(db.engine, "connect") as connect:
        page = client.get("/")
        connect.assert_not_called()
    assert page.status_code == 200
    assert "Less waiting." in page.text and "More learning." in page.text
    elements = Elements(page.text)
    assert elements.find("html")[0]["lang"] == "en"
    assert len(elements.find("h1")) == 1
    assert elements.find("main")[0]["id"] == "main-content"
    assert elements.find("nav")[0]["aria-label"]
    assert elements.find("footer")
    assert not elements.find("script")
    links = [a["href"] for a in elements.find("a")]
    assert "#main-content" in links
    with app.test_request_context():
        assert links.count(url_for("auth.signup")) == 2
        assert links.count(url_for("auth.login")) == 2
    assert "Get Started" in page.text and "Sign Up" in page.text and "Log In" in page.text
    assert client.get("/instructor/dashboard").status_code == 302


def test_landing_hero_and_styles_are_local_and_load(client):
    elements = Elements(client.get("/").text)
    hero = elements.find("img")[0]
    assert hero["alt"] and hero["width"] == "1672" and hero["height"] == "941"
    assert hero["fetchpriority"] == "high"
    assert hero["src"].startswith("/static/images/")
    sources = {hero["src"], *(item.strip().split()[0] for item in hero["srcset"].split(","))}
    assert len(sources) == 2 and hero["sizes"]
    for source in sources:
        assert source.startswith("/static/images/")
        response = client.get(source)
        assert response.status_code == 200 and response.mimetype == "image/webp"
        assert response.data[:4] == b"RIFF" and response.data[8:12] == b"WEBP"
    for stylesheet in elements.find("link"):
        assert stylesheet["href"].startswith("/static/css/")
        response = client.get(stylesheet["href"])
        assert response.status_code == 200 and response.mimetype == "text/css"


def test_authenticated_landing_keeps_dashboard_and_secure_logout(
    client, auth_db, signup_data, post_form, csrf_token
):
    assert post_form(client, "/auth/signup", signup_data).location == "/auth/login"
    assert post_form(client, "/auth/login", signup_data).location == "/instructor/dashboard"
    page = client.get("/")
    assert page.status_code == 200 and "Less waiting." in page.text
    assert "Open instructor dashboard" in page.text
    links = [a["href"] for a in Elements(page.text).find("a")]
    assert "/instructor/dashboard" in links and "/instructor/settings" in links
    assert client.get("/instructor/dashboard").status_code == 200
    assert client.get("/auth/login").location == "/instructor/dashboard"
    assert client.post("/auth/logout").status_code == 400
    assert client.post("/auth/logout", data={"csrf_token": csrf_token(page)}).status_code == 302
    assert client.get("/instructor/dashboard").status_code == 302


@pytest.mark.parametrize("category", ["message", "success", "warning", "error", "info"])
def test_shared_flash_messages_are_accessible_and_escaped(client, category):
    with client.session_transaction() as session:
        session["_flashes"] = [(category, "Saved <script>unsafe</script>")]
    page = client.get("/")
    assert "Saved &lt;script&gt;unsafe&lt;/script&gt;" in page.text
    kind = {"message": "info", "error": "danger"}.get(category, category)
    assert f'class="alert alert--{kind}"' in page.text
    assert f'role="{"alert" if category == "error" else "status"}"' in page.text
    assert "Saved" not in client.get("/").text


def test_shared_form_errors_keep_labels_and_descriptions(client, csrf_token):
    page = client.get("/auth/login")
    response = client.post("/auth/login", data={"csrf_token": csrf_token(page)})
    assert response.status_code == 400
    elements = Elements(response.text)
    labels = {label["for"] for label in elements.find("label")}
    ids = {attrs["id"] for _, attrs in elements.tags if "id" in attrs}
    for field in elements.find("input"):
        if field.get("type") in {"email", "password"}:
            assert field["id"] in labels
            assert field["aria-invalid"] == "true"
            assert field["aria-describedby"] in ids
    assert 'role="alert"' in response.text
