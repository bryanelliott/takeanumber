from flask import Blueprint, abort, make_response, redirect, render_template, url_for

from app.queue import browser
from app.queue.forms import JoinForm, LeaveForm
from app.services import queue, sessions, student_identity

blueprint = Blueprint("queue", __name__, url_prefix="/session")


@blueprint.after_request
def protect_private_state(response):
    response.headers["Cache-Control"] = "no-store"
    # HTTPS CSRF checks need a same-origin referrer; keep it hidden from other sites.
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@blueprint.errorhandler(sessions.SessionNotFound)
@blueprint.errorhandler(queue.EntryNotFound)
def not_found(error):
    return render_template("queue/error.html", message="Session or request not found."), 404


def render_client(public_code, token, *, join_form=None, error=None, status=200, fragment=False):
    state = queue.client_state(public_code, token)
    binding = browser.form_binding(token, public_code)
    return make_response(
        render_template(
            "queue/_client_state.html" if fragment else "queue/client.html",
            state=state,
            error=error,
            join_form=join_form or JoinForm(data={"browser_binding": binding}),
            leave_form=LeaveForm(data={"browser_binding": binding, "entry_id": state.entry_id}),
        ),
        status,
    )


def browser_error(public_code):
    return render_template(
        "queue/error.html",
        public_code=public_code,
        message="Your browser cookie is missing, expired, or changed. Allow cookies and reopen "
        "the session before trying again. A previous request may still be waiting.",
    ), 409


@blueprint.get("/<public_code>")
def client(public_code):
    token = browser.read_token() or student_identity.new_token()
    response = render_client(public_code, token)
    browser.write_cookie(response, token)
    return response


@blueprint.get("/<public_code>/state")
def live_state(public_code):
    # Read the current HTTP cookie, never a browser identifier supplied over a socket.
    token = browser.read_token()
    if not token:
        return browser_error(public_code)
    return render_client(public_code, token, fragment=True)


@blueprint.post("/<public_code>/join")
def join(public_code):
    token = browser.read_token()
    form = JoinForm()
    if not token:
        return browser_error(public_code)
    if not form.validate_on_submit():
        return render_client(public_code, token, join_form=form, status=400)
    if not browser.binding_matches(form.browser_binding.data, token, public_code):
        return browser_error(public_code)
    try:
        queue.join(public_code, token, form.display_name.data)
    except sessions.SessionEnded:
        return render_client(public_code, token, status=409)
    return redirect(url_for("queue.client", public_code=public_code), code=303)


@blueprint.post("/<public_code>/leave")
def leave(public_code):
    token = browser.read_token()
    form = LeaveForm()
    if not token:
        return browser_error(public_code)
    if not form.validate_on_submit():
        abort(400)
    if not browser.binding_matches(form.browser_binding.data, token, public_code):
        return browser_error(public_code)
    try:
        queue.leave(public_code, token, form.entry_id.data)
    except sessions.SessionEnded:
        return render_client(public_code, token, status=409)
    return redirect(url_for("queue.client", public_code=public_code), code=303)


@blueprint.get("/<public_code>/exit")
def exit_view(public_code):
    # Read-only, including database timestamps. Exit never invokes Leave Queue.
    state = queue.client_state(public_code, browser.read_token())
    return render_template("queue/exit.html", state=state)
