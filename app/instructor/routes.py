from flask import Blueprint, abort, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.services import sessions

blueprint = Blueprint("instructor", __name__, url_prefix="/instructor")


@blueprint.get("/dashboard")
@login_required
def dashboard():
    return render_template(
        "instructor/dashboard.html", active_session=sessions.active_session(current_user.id)
    )


@blueprint.post("/sessions")
@login_required
def start_session():
    try:
        help_session = sessions.start_session(current_user.id)
    except sessions.SessionNotFound:
        abort(404)
    return redirect(url_for("instructor.master", public_code=help_session.public_code))


@blueprint.get("/sessions/<public_code>/master")
@login_required
def master(public_code):
    try:
        help_session = sessions.owned_session(current_user.id, public_code)
    except sessions.SessionNotFound:
        abort(404)
    return render_template("instructor/master.html", help_session=help_session)


@blueprint.post("/sessions/<public_code>/end")
@login_required
def end_session(public_code):
    try:
        help_session = sessions.end_session(current_user.id, public_code)
    except sessions.SessionNotFound:
        abort(404)
    return redirect(url_for("instructor.master", public_code=help_session.public_code))
