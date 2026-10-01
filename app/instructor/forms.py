from flask_wtf import FlaskForm
from wtforms import BooleanField, HiddenField, SelectField, SubmitField
from wtforms.validators import UUID, InputRequired


class AdvanceForm(FlaskForm):
    entry_id = HiddenField(validators=[InputRequired(), UUID()])


class SettingsForm(FlaskForm):
    alert_next_enabled = BooleanField("Alert Next Up and advance warnings")
    alert_serving_enabled = BooleanField("Alert Currently Serving")
    visual_alert_enabled = BooleanField("Emphasize visual alerts")
    sound_alert_enabled = BooleanField("Allow optional sound")
    vibration_enabled = BooleanField("Allow optional vibration where supported")
    advance_warning_count = SelectField(
        "Advance warning distance",
        coerce=int,
        choices=[(1, "1 — Next Up only"), (2, "2 waiting requests"), (3, "3 waiting requests")],
        validators=[InputRequired()],
    )
    submit = SubmitField("Save settings")
