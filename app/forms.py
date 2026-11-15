"""
Web forms. Flask-WTF checks every field (validators) and adds a hidden CSRF
token to each form, so other websites can't submit forms on a user's behalf.
"""
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (BooleanField, DateField, EmailField, IntegerField, PasswordField, SelectField,
                     StringField, SubmitField)
from wtforms.validators import DataRequired, Email, InputRequired, Length, NumberRange, Optional
from wtforms.widgets import HiddenInput

from ml import CLASS_NAMES

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


class DentistFindingForm(FlaskForm):
    """
    A finding the dentist adds by hand. The box (x1, y1, x2, y2, in image pixels) is
    filled in by static/app.js when the dentist draws on the X-ray.
    """
    label = SelectField("Finding", choices=[(n, n) for n in CLASS_NAMES], validators=[DataRequired()])
    note = StringField("Note (optional)", validators=[Optional(), Length(max=300)])
    x1 = IntegerField(widget=HiddenInput(), validators=[InputRequired(), NumberRange(min=0)])
    y1 = IntegerField(widget=HiddenInput(), validators=[InputRequired(), NumberRange(min=0)])
    x2 = IntegerField(widget=HiddenInput(), validators=[InputRequired(), NumberRange(min=0)])
    y2 = IntegerField(widget=HiddenInput(), validators=[InputRequired(), NumberRange(min=0)])
    submit = SubmitField("Save finding")
