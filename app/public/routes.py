from flask import Blueprint, render_template

blueprint = Blueprint("public", __name__)


@blueprint.get("/")
def landing():
    return render_template("public/landing.html")
