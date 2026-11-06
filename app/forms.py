"""
Web forms. Flask-WTF checks every field (validators) and adds a hidden CSRF
token to each form, so other websites can't submit forms on a user's behalf.
"""
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import BooleanField, DateField, EmailField, PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Optional

ALLOWED_IMAGE_TYPES = ["jpg", "jpeg", "png"]


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log in")


class DoctorForm(FlaskForm):
    """Used by the admin to add or edit a doctor."""
    name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    phone = StringField("Phone", validators=[Optional(), Length(max=30)])
    password = PasswordField("Password", validators=[Optional(), Length(min=8)])
    submit = SubmitField("Save")


class TransferForm(FlaskForm):
    """Pick the doctor who takes over one patient."""
    new_doctor = SelectField("Transfer to", coerce=int, validators=[DataRequired()])
    submit = SubmitField("Transfer patient")


class ReassignForm(FlaskForm):
    """Admin: move ALL patients of a doctor, and optionally remove that doctor afterwards."""
    new_doctor = SelectField("Move all patients to", coerce=int, validators=[DataRequired()])
    remove_doctor = BooleanField("Also remove this doctor afterwards")
    submit = SubmitField("Transfer patients")


class PatientForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    email = EmailField("Email", validators=[Optional(), Email(), Length(max=120)])
    phone = StringField("Phone", validators=[Optional(), Length(max=30)])
    dob = DateField("Date of birth", validators=[Optional()])
    submit = SubmitField("Save patient")


class XRayUploadForm(FlaskForm):
    image = FileField("Panoramic X-ray (JPEG or PNG)", validators=[
        FileRequired(), FileAllowed(ALLOWED_IMAGE_TYPES, "Only JPEG or PNG images are allowed.")])
    submit = SubmitField("Upload X-ray")


class ConfirmForm(FlaskForm):
    """An empty form, used for buttons (delete, send) so they still carry a CSRF token."""
    submit = SubmitField("Confirm")
