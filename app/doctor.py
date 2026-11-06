"""
Doctor dashboard: patients, X-rays, diagnosis and sending results to patients.
Every route is protected by @role_required("doctor"), and a doctor can only
open their OWN patients (anything else gives 404, as if it didn't exist).
"""
import smtplib

from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request, send_file,
                   url_for)
from flask_login import current_user

from app.analysis import REVIEW_CHOICES, review_counts, run_analysis, set_review
from app.auth import role_required
from app.inference import ModelNotFound, annotated_name
from app.emailer import email_configured, send_email
from app.extensions import db
from app.forms import ConfirmForm, PatientForm, TransferForm, XRayUploadForm
from app.models import Patient, XRayImage
from app.recommendations import assess_xray
from app.stats import doctor_stats, xrays_to_review
from app.storage import InvalidImage, save_upload, upload_path
from app.transfers import doctor_choices, other_doctors, transfer_patient

bp = Blueprint("doctor", __name__)

# Same colours as the boxes drawn in app/inference.py, as CSS colours for the findings list.
FINDING_COLOURS = {"Caries": "#e62828", "Periapical lesion": "#ffc800",
                   "Impacted tooth": "#1ea0e6", "Bone Loss": "#3cc83c"}


def own_patient_or_404(patient_id):
    return Patient.query.filter_by(id=patient_id, dentist_id=current_user.id).first_or_404()


def own_xray_or_404(xray_id):
    return XRayImage.query.join(Patient).filter(
        XRayImage.id == xray_id, Patient.dentist_id == current_user.id).first_or_404()


@bp.route("/")
@role_required("doctor")
def dashboard():
    """The doctor's home page: their patient list."""
    patients = Patient.query.filter_by(dentist_id=current_user.id).order_by(Patient.name).all()
    to_review, review_total = xrays_to_review(current_user.id)
    return render_template("doctor/dashboard.html", patients=patients, stats=doctor_stats(current_user.id),
                           to_review=to_review, review_total=review_total)


@bp.route("/patients/new", methods=["GET", "POST"])
@role_required("doctor")
def add_patient():
    form = PatientForm()
    if form.validate_on_submit():
        patient = Patient(name=form.name.data, email=form.email.data or None,
                          phone=form.phone.data, dob=form.dob.data, dentist_id=current_user.id)
        db.session.add(patient)
        db.session.commit()
        flash(f"Patient {patient.name} added.", "success")
        return redirect(url_for("doctor.patient", patient_id=patient.id))
    return render_template("doctor/patient_form.html", form=form, title="Add patient")


@bp.route("/patients/<int:patient_id>/edit", methods=["GET", "POST"])
@role_required("doctor")
def edit_patient(patient_id):
    patient = own_patient_or_404(patient_id)
    form = PatientForm(obj=patient)
    if form.validate_on_submit():
        form.populate_obj(patient)
        patient.email = patient.email or None
        db.session.commit()
        flash("Patient details saved.", "success")
        return redirect(url_for("doctor.patient", patient_id=patient.id))
    return render_template("doctor/patient_form.html", form=form, title=f"Edit {patient.name}")


@bp.route("/patients/<int:patient_id>/transfer", methods=["GET", "POST"])
@role_required("doctor")
def transfer_patient_view(patient_id):
    """Give one of MY patients to another doctor. Afterwards I can no longer open them."""
    patient = own_patient_or_404(patient_id)
    others = other_doctors(current_user.id)
    form = TransferForm()
    form.new_doctor.choices = doctor_choices(others)
    if others and form.validate_on_submit():
        new_doctor = next(d for d in others if d.id == form.new_doctor.data)
        transfer_patient(patient, new_doctor)
        db.session.commit()
        flash(f"{patient.name} has been transferred to {new_doctor.name}.", "success")
        return redirect(url_for("doctor.dashboard"))
    return render_template("transfer.html", patient=patient, form=form, has_others=bool(others),
                           cancel_url=url_for("doctor.patient", patient_id=patient.id))


@bp.route("/patients/<int:patient_id>", methods=["GET", "POST"])
@role_required("doctor")
def patient(patient_id):
    """Patient details, their X-ray history, and the upload form."""
    patient = own_patient_or_404(patient_id)
    form = XRayUploadForm()
    if form.validate_on_submit():
        try:
            file_name = save_upload(form.image.data)
        except InvalidImage as error:
            form.image.errors.append(str(error))
        else:
            xray = XRayImage(patient=patient, dentist_id=current_user.id, image_path=file_name)
            db.session.add(xray)
            db.session.commit()
            flash("X-ray uploaded.", "success")
            analyse_and_report(xray)
            return redirect(url_for("doctor.xray", xray_id=xray.id))
    return render_template("doctor/patient.html", patient=patient, form=form)


@bp.route("/xrays/<int:xray_id>")
@role_required("doctor")
def xray(xray_id):
    """One X-ray with its AI diagnosis (when available) and the send options."""
    xray = own_xray_or_404(xray_id)
    return render_template("doctor/xray.html", xray=xray, confirm=ConfirmForm(),
                           report=latest_report(xray), colours=FINDING_COLOURS,
                           reviews=review_counts(xray.result.findings) if xray.result else None,
                           can_email=email_configured() and bool(xray.patient.email),
                           assessment=assess_xray(xray, upload_path(xray.image_path)))


def analyse_and_report(xray):
    """Run the AI on an X-ray and tell the doctor how it went (never crashes the page)."""
    try:
        seconds = run_analysis(xray, current_user)
        flash(f"AI analysis finished in {seconds:.1f} seconds.", "success")
    except ModelNotFound:
        flash("The AI model file (models/best.pt) is missing, so the X-ray was saved without analysis.",
              "error")
    except Exception:                                   # keep the upload even if analysis fails
        db.session.rollback()
        current_app.logger.exception("Analysis failed for X-ray %s", xray.id)
        flash("The AI analysis failed. The X-ray is saved; try 'Run AI analysis' again.", "error")


@bp.route("/xrays/<int:xray_id>/analyse", methods=["POST"])
@role_required("doctor")
def analyse_xray(xray_id):
    """Run (or re-run) the AI on an existing X-ray."""
    xray = own_xray_or_404(xray_id)
    if ConfirmForm().validate_on_submit():
        analyse_and_report(xray)
    return redirect(url_for("doctor.xray", xray_id=xray.id))


@bp.route("/xrays/<int:xray_id>/findings/<int:index>/review", methods=["POST"])
@role_required("doctor")
def review_finding(xray_id, index):
    """The dentist agrees or disagrees with one AI finding (human-in-the-loop)."""
    xray = own_xray_or_404(xray_id)
    decision = request.form.get("decision")
    if xray.result is None or not 0 <= index < len(xray.result.findings) or decision not in REVIEW_CHOICES:
        abort(400)
    if ConfirmForm().validate_on_submit():
        set_review(xray, index, decision, current_user)
    return redirect(url_for("doctor.xray", xray_id=xray.id))


@bp.route("/xrays/<int:xray_id>/image")
@role_required("doctor")
def xray_image(xray_id):
    """Serve the image file, only to its own doctor (files are not public)."""
    xray = own_xray_or_404(xray_id)
    return send_file(upload_path(xray.image_path))


@bp.route("/xrays/<int:xray_id>/annotated")
@role_required("doctor")
def annotated_image(xray_id):
    """The X-ray with the AI's boxes drawn on it."""
    xray = own_xray_or_404(xray_id)
    path = upload_path(annotated_name(xray.image_path))
    if xray.result is None or not path.exists():
        abort(404)
    return send_file(path)


@bp.route("/xrays/<int:xray_id>/report")
@role_required("doctor")
def download_report(xray_id):
    """Download the latest PDF report of an X-ray."""
    xray = own_xray_or_404(xray_id)
    report = latest_report(xray)
    if report is None or not upload_path(report.file_path).exists():
        abort(404)
    name = f"SmartDent_report_{xray.patient.name.replace(' ', '_')}_{xray.upload_date:%Y%m%d}.pdf"
    return send_file(upload_path(report.file_path), as_attachment=True, download_name=name)


def latest_report(xray):
    """The newest report of an X-ray, or None."""
    if xray.result is None or not xray.result.reports:
        return None
    return max(xray.result.reports, key=lambda r: r.report_date)


@bp.route("/xrays/<int:xray_id>/download")
@role_required("doctor")
def download_xray(xray_id):
    """Download the X-ray, e.g. to give it to the patient when email is not set up."""
    xray = own_xray_or_404(xray_id)
    name = f"xray_{xray.patient.name.replace(' ', '_')}_{xray.upload_date:%Y%m%d}{upload_path(xray.image_path).suffix}"
    return send_file(upload_path(xray.image_path), as_attachment=True, download_name=name)


@bp.route("/xrays/<int:xray_id>/send", methods=["POST"])
@role_required("doctor")
def send_xray(xray_id):
    """Email the X-ray (and the report, once Phase 5 creates one) to the patient."""
    xray = own_xray_or_404(xray_id)
    if not ConfirmForm().validate_on_submit():
        flash("The request could not be verified. Please try again.", "error")
    elif not email_configured():
        flash("Email is not set up. Use Download and give the file to the patient.", "error")
    elif not xray.patient.email:
        flash("This patient has no email address. Add one first.", "error")
    else:
        try:
            send_email(xray.patient.email, "Your dental X-ray from SmartDent",
                       f"Dear {xray.patient.name},\n\nPlease find your dental X-ray attached.\n\n"
                       f"{current_user.name}", attachments=xray_attachments(xray))
            flash(f"Sent to {xray.patient.email}.", "success")
        except (smtplib.SMTPException, OSError):
            flash("The email could not be sent. Check the email settings or use Download.", "error")
    return redirect(url_for("doctor.xray", xray_id=xray.id))


def xray_attachments(xray):
    """The files to send: the X-ray, plus any report PDFs."""
    files = [upload_path(xray.image_path)]
    if xray.result:
        files += [upload_path(r.file_path) for r in xray.result.reports if r.file_path]
    return files
