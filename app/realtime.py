"""Session-scoped invalidations only; private state is read through HTTP."""

import re

from flask import current_app, request
from flask_login import current_user
from flask_socketio import join_room
from flask_wtf.csrf import validate_csrf
from wtforms.validators import ValidationError

from app.extensions import db
from app.models import HelpSession


def room(public_code, view):
    return f"{'master' if view == 'master' else 'session'}:{public_code}"


def connect(auth):
    # before_request/CSRFProtect do not run for Socket.IO handlers.
    if not isinstance(auth, dict):
        return False
    code, view, csrf = auth.get("public_code"), auth.get("view"), auth.get("csrf_token")
    if (
        not isinstance(code, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{22}", code)
        or view not in ("client", "master")
        or not isinstance(csrf, str)
        or len(csrf) > 256
    ):
        return False
    origin = request.headers.get("Origin")
    if origin is not None and origin != request.host_url.rstrip("/"):
        return False
    try:
        validate_csrf(csrf)
    except ValidationError:
        return False
    try:
        query = db.select(HelpSession.public_code).where(HelpSession.public_code == code)
        if view == "master":
            if not current_user.is_authenticated:
                return False
            query = query.where(HelpSession.instructor_id == current_user.id)
        if db.session.scalar(query) is None:
            return False
        # Clients cannot supply a room name, switch rooms, or mutate the queue.
        join_room(room(code, view))
    finally:
        db.session.rollback()  # release the read transaction for this handshake


def publish_queue_changed(public_code):
    """Call only after commit; transport failure must not undo successful work."""
    try:
        socketio = current_app.extensions["socketio"]
        for view in ("client", "master"):
            socketio.emit("queue_changed", {}, to=room(public_code, view), namespace="/")
    except Exception:
        # No tokens, names, cookies, or exception contents in the log.
        current_app.logger.warning("Queue update delivery failed; views will reconcile on refresh.")
