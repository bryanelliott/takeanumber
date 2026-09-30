from flask import Blueprint, flash, redirect, render_template, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.auth.forms import LoginForm, SignupForm
from app.auth.services import EmailAlreadyRegistered, authenticate, register_instructor

blueprint = Blueprint("auth", __name__, url_prefix="/auth")


@blueprint.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("instructor.dashboard"))
    form = SignupForm()
    if form.validate_on_submit():
        try:
            register_instructor(form.email.data, form.display_name.data, form.password.data)
        except EmailAlreadyRegistered as error:
            form.email.errors.append(str(error))
            return render_template("auth/signup.html", form=form), 409
        flash("Instructor account created. Please log in.")
        return redirect(url_for("auth.login"))
    return render_template("auth/signup.html", form=form), 400 if form.is_submitted() else 200


@blueprint.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("instructor.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        instructor = authenticate(form.email.data, form.password.data)
        if instructor:
            session.clear()
            login_user(instructor, remember=False)
            # The dashboard is the only protected destination in this milestone.
            # Ignore arbitrary `next` values so authentication cannot create open redirects.
            return redirect(url_for("instructor.dashboard"))
        form.password.errors.append("Invalid email or password.")
        return render_template("auth/login.html", form=form), 401
    return render_template("auth/login.html", form=form), 400 if form.is_submitted() else 200


@blueprint.post("/logout")
@login_required
def logout():
    # Global CSRF protection validates the token before this route executes.
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))
