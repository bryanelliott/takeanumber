"""Fixtures always opt into the dedicated PostgreSQL test configuration."""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from flask_migrate import upgrade
from sqlalchemy import text

from app import create_app
from app.auth.services import register_instructor
from app.extensions import db
from app.models import HelpSession, Instructor, QueueEntry, StudentIdentity
from app.services import sessions

MIGRATIONS = str(Path(__file__).resolve().parents[1] / "migrations")


@pytest.fixture(scope="session")
def migrated_schema():
    application = create_app({"TESTING": True, "SECRET_KEY": "test-only-secret"})
    with application.app_context():
        # Verify the actual target before executing schema changes.
        with db.engine.connect() as connection:
            database, username = connection.execute(
                text("SELECT current_database(), current_user")
            ).one()
            assert database == db.engine.url.database and database.endswith("_test")
            assert username == db.engine.url.username and username.endswith("_test")
        upgrade(directory=MIGRATIONS)
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def app():
    application = create_app({"TESTING": True, "SECRET_KEY": "test-only-secret"})
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_db(app, migrated_schema):
    # Only the already-validated dedicated test database is modified here.
    with app.app_context():
        db.session.execute(db.delete(QueueEntry))
        db.session.execute(db.delete(StudentIdentity))
        db.session.execute(db.delete(HelpSession))
        db.session.execute(db.delete(Instructor))
        db.session.commit()
    yield
    with app.app_context():
        db.session.rollback()
        db.session.execute(db.delete(QueueEntry))
        db.session.execute(db.delete(StudentIdentity))
        db.session.execute(db.delete(HelpSession))
        db.session.execute(db.delete(Instructor))
        db.session.commit()


@pytest.fixture
def signup_data():
    return {
        "email": "faculty@example.edu",
        "display_name": "Faculty Example",
        "password": "a sufficiently long password",
        "confirm_password": "a sufficiently long password",
    }


@pytest.fixture
def csrf_token():
    def extract(response):
        match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text)
        assert match, response.text
        return match.group(1)

    return extract


@pytest.fixture
def post_form(csrf_token):
    def submit(client, path, data):
        token = csrf_token(client.get(path))
        return client.post(path, data={**data, "csrf_token": token})

    return submit


@pytest.fixture
def queue_session(app, auth_db):
    with app.app_context():
        owner = register_instructor("queue@example.edu", "Queue Instructor", "a long test password")
        owner_id = owner.id
        code = sessions.start_session(owner_id).public_code
        return owner_id, code


@pytest.fixture
def hidden_fields():
    class Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.fields = {}

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag == "input" and values.get("type") == "hidden":
                self.fields[values["name"]] = values.get("value", "")

    def extract(response):
        parser = Parser()
        parser.feed(response.text)
        return parser.fields

    return extract
