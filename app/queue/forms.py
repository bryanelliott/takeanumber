from flask_wtf import FlaskForm
from wtforms import HiddenField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional


class BrowserForm(FlaskForm):
    browser_binding = HiddenField(validators=[DataRequired(), Length(min=64, max=64)])


class JoinForm(BrowserForm):
    display_name = StringField("Name (optional)", validators=[Optional(), Length(max=100)])
    submit = SubmitField("Take A Number")


class LeaveForm(BrowserForm):
    entry_id = HiddenField(validators=[DataRequired(), Length(max=36)])
    submit = SubmitField("Leave Queue")
