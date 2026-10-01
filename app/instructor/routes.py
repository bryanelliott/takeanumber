import qrcode
from flask import Blueprint, Response, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from qrcode.image.svg import SvgPathFillImage

from app.instructor.forms import AdvanceForm
from app.services import queue, sessions

blueprint = Blueprint("instructor", __name__, url_prefix="/instructor")


@blueprint.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


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
        state = queue.master_state(current_user.id, public_code)
    except sessions.SessionNotFound:
        abort(404)
    return render_template(
        "instructor/master.html",
        state=state,
        client_url=url_for("queue.client", public_code=public_code, _external=True),
    )


@blueprint.get("/sessions/<public_code>/qr.svg")
@login_required
def session_qr(public_code):
    try:
        help_session = sessions.owned_session(current_user.id, public_code)
    except sessions.SessionNotFound:
        abort(404)
    if help_session.status != "active":
        abort(404)
    client_url = url_for("queue.client", public_code=public_code, _external=True)
    image = qrcode.make(client_url, image_factory=SvgPathFillImage, border=4)
    return Response(image.to_string(), mimetype="image/svg+xml")


@blueprint.get("/sessions/<public_code>/state")
@login_required
def live_state(public_code):
    try:
        state = queue.master_state(current_user.id, public_code)
    except sessions.SessionNotFound:
        abort(404)
    return render_template(
        "instructor/_master_state.html",
        state=state,
        client_url=url_for("queue.client", public_code=public_code, _external=True),
    )


@blueprint.post("/sessions/<public_code>/serve-next")
@login_required
def serve_next(public_code):
    return _advance_response(public_code, queue.begin_serving)


@blueprint.post("/sessions/<public_code>/done")
@login_required
def done(public_code):
    return _advance_response(public_code, queue.complete_current)


def _advance_response(public_code, operation):
    form = AdvanceForm()
    if not form.validate_on_submit():
        abort(400)
    try:
        changed = operation(current_user.id, public_code, form.entry_id.data)
    except sessions.SessionNotFound:
        abort(404)
    except sessions.SessionEnded:
        abort(409, description="This session has ended. Refresh the Master View.")
    if not changed:
        flash("The queue changed or this action was already applied. Review the current state.")
    return redirect(url_for("instructor.master", public_code=public_code), code=303)


@blueprint.post("/sessions/<public_code>/end")
@login_required
def end_session(public_code):
    try:
        help_session = sessions.end_session(current_user.id, public_code)
    except sessions.SessionNotFound:
        abort(404)
    return redirect(url_for("instructor.master", public_code=help_session.public_code))
