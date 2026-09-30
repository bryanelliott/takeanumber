"""Fixtures always opt into the dedicated PostgreSQL test configuration."""

import pytest

from app import create_app
from app.extensions import db


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
