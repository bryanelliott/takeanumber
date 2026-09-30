from flask import Blueprint, render_template
from flask_login import login_required

blueprint = Blueprint("instructor", __name__, url_prefix="/instructor")


@blueprint.get("/dashboard")
@login_required
def dashboard():
    return render_template("instructor/dashboard.html")
