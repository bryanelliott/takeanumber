from flask_wtf import FlaskForm
from wtforms import HiddenField
from wtforms.validators import UUID, InputRequired


class AdvanceForm(FlaskForm):
    entry_id = HiddenField(validators=[InputRequired(), UUID()])
