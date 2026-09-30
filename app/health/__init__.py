"""Health blueprint."""

from flask import Blueprint

blueprint = Blueprint("health", __name__)

from app.health import routes  # noqa: E402, F401
