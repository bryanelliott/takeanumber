"""Signed, HttpOnly browser cookie, separate from the instructor login session."""

import hashlib
import hmac

from flask import current_app, request
from itsdangerous import BadData, URLSafeTimedSerializer

from app.services.student_identity import valid_token

COOKIE_NAME = "tan_browser"
COOKIE_PATH = "/session"


def serializer():
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt="student-browser-v1",
        signer_kwargs={"digest_method": hashlib.sha256},
    )


def read_token():
    value = request.cookies.get(COOKIE_NAME)
    if not value or len(value) > 256:
        return None
    try:
        token = serializer().loads(value, max_age=current_app.config["STUDENT_COOKIE_MAX_AGE"])
    except BadData:
        return None
    return token if valid_token(token) else None


def write_cookie(response, token):
    response.set_cookie(
        COOKIE_NAME,
        serializer().dumps(token),
        path=COOKIE_PATH,
        max_age=current_app.config["STUDENT_COOKIE_MAX_AGE"],
        httponly=True,
        secure=current_app.config["SESSION_COOKIE_SECURE"],
        samesite="Lax",
    )


def form_binding(token, public_code):
    """Bind rendered forms to this cookie and session, including first-visit races."""
    key = current_app.config["SECRET_KEY"]
    if isinstance(key, str):
        key = key.encode()
    message = f"student-form:{public_code}:{token}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def binding_matches(value, token, public_code):
    return hmac.compare_digest((value or "").encode(), form_binding(token, public_code).encode())
