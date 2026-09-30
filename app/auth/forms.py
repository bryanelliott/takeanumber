from flask_wtf import FlaskForm
from wtforms import EmailField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length, ValidationError

from app.models.instructor import normalize_email


def strip_text(value):
    return value.strip() if value else value


class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Length(max=254)], filters=[strip_text])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])
    submit = SubmitField("Log in")

    def validate_email(self, field):
        try:
            field.data = normalize_email(field.data)
        except ValueError as error:
            raise ValidationError(str(error)) from None


class SignupForm(LoginForm):
    display_name = StringField(
        "Display name", validators=[DataRequired(), Length(max=100)], filters=[strip_text]
    )
    password = PasswordField("Password", validators=[DataRequired(), Length(min=15, max=128)])
    confirm_password = PasswordField(
        "Confirm password", validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField("Create instructor account")
