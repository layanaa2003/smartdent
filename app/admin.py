"""
Admin dashboard: add, edit and remove doctors, view all patients, and transfer
patients between doctors.
Every route here is protected by @role_required("admin").
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.auth import role_required
from app.extensions import db
from app.forms import ConfirmForm, DoctorForm, ReassignForm, TransferForm
from app.models import ROLE_DOCTOR, Dentist, Patient
from app.stats import admin_stats
from app.transfers import (doctor_choices, hand_over_records, other_doctors, transfer_all_patients,
                           transfer_patient)

bp = Blueprint("admin", __name__)


def get_doctor_or_404(doctor_id):
    """Find a doctor by id; admins are not doctors, so they give 404 too."""
    return Dentist.query.filter_by(id=doctor_id, role=ROLE_DOCTOR).first_or_404()


def email_taken(email, except_id=None):
    """True if another account already uses this email."""
    existing = Dentist.query.filter_by(email=email).first()
    return existing is not None and existing.id != except_id


@bp.route("/doctors")
@role_required("admin")
def doctors():
    all_doctors = Dentist.query.filter_by(role=ROLE_DOCTOR).order_by(Dentist.name).all()
    return render_template("admin/doctors.html", doctors=all_doctors, confirm=ConfirmForm(),
                           stats=admin_stats())


@bp.route("/doctors/new", methods=["GET", "POST"])
@role_required("admin")
def add_doctor():
    form = DoctorForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if not form.password.data:
            form.password.errors.append("A new doctor needs a password.")
        elif email_taken(email):
            form.email.errors.append("This email is already used.")
        else:
            doctor = Dentist(name=form.name.data, email=email, phone=form.phone.data, role=ROLE_DOCTOR)
            doctor.set_password(form.password.data)
            db.session.add(doctor)
            db.session.commit()
            flash(f"Doctor {doctor.name} added.", "success")
            return redirect(url_for("admin.doctors"))
    return render_template("admin/doctor_form.html", form=form, title="Add doctor")


@bp.route("/doctors/<int:doctor_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def edit_doctor(doctor_id):
    doctor = get_doctor_or_404(doctor_id)
    form = DoctorForm(obj=doctor)
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if email_taken(email, except_id=doctor.id):
            form.email.errors.append("This email is already used.")
        else:
            doctor.name, doctor.email, doctor.phone = form.name.data, email, form.phone.data
            if form.password.data:                       # empty = keep the old password
                doctor.set_password(form.password.data)
            db.session.commit()
            flash(f"Doctor {doctor.name} updated.", "success")
            return redirect(url_for("admin.doctors"))
    return render_template("admin/doctor_form.html", form=form, title=f"Edit {doctor.name}",
                           editing=True)


@bp.route("/doctors/<int:doctor_id>/delete", methods=["POST"])
@role_required("admin")
def delete_doctor(doctor_id):
    """Remove a doctor. If they still have patients, those must be moved first."""
    doctor = get_doctor_or_404(doctor_id)
    if not ConfirmForm().validate_on_submit():
        flash("The request could not be verified. Please try again.", "error")
    elif doctor.patients:
        return redirect(url_for("admin.reassign_patients", doctor_id=doctor.id, remove=1))
    else:
        db.session.delete(doctor)
        db.session.commit()
        flash(f"Doctor {doctor.name} removed.", "success")
    return redirect(url_for("admin.doctors"))


@bp.route("/doctors/<int:doctor_id>/reassign", methods=["GET", "POST"])
@role_required("admin")
def reassign_patients(doctor_id):
    """
    Move ALL of a doctor's patients to another doctor. The admin can keep the doctor
    (e.g. they are on leave) or tick the box to remove them afterwards.
    Arriving here from "Remove" pre-ticks the box.
    """
    doctor = get_doctor_or_404(doctor_id)
    others = other_doctors(doctor.id)
    form = ReassignForm()
    form.new_doctor.choices = doctor_choices(others)
    if request.method == "GET" and request.args.get("remove"):
        form.remove_doctor.data = True
    if others and form.validate_on_submit():
        new_doctor = get_doctor_or_404(form.new_doctor.data)
        moved = transfer_all_patients(doctor, new_doctor)
        if form.remove_doctor.data:
            hand_over_records(doctor, new_doctor)
            db.session.delete(doctor)
            message = f"{moved} patient(s) moved to {new_doctor.name} and {doctor.name} removed."
        else:
            message = f"{moved} patient(s) moved from {doctor.name} to {new_doctor.name}."
        db.session.commit()
        flash(message, "success")
        return redirect(url_for("admin.doctors"))
    return render_template("admin/reassign.html", doctor=doctor, form=form, has_others=bool(others))


@bp.route("/patients")
@role_required("admin")
def patients():
    all_patients = Patient.query.order_by(Patient.name).all()
    return render_template("admin/patients.html", patients=all_patients)


@bp.route("/patients/<int:patient_id>/transfer", methods=["GET", "POST"])
@role_required("admin")
def transfer_patient_view(patient_id):
    """Admin: give any one patient to a different doctor."""
    patient = db.get_or_404(Patient, patient_id)
    others = other_doctors(patient.dentist_id)
    form = TransferForm()
    form.new_doctor.choices = doctor_choices(others)
    # Opened from a doctor's transfer page (?back=<doctor id>)? Then return there afterwards.
    back_doctor = request.args.get("back", type=int)
    back_url = (url_for("admin.reassign_patients", doctor_id=back_doctor) if back_doctor
                else url_for("admin.patients"))
    if others and form.validate_on_submit():
        new_doctor = get_doctor_or_404(form.new_doctor.data)
        old_doctor = patient.dentist
        transfer_patient(patient, new_doctor)
        db.session.commit()
        flash(f"{patient.name} transferred from {old_doctor.name} to {new_doctor.name}.", "success")
        if back_doctor and old_doctor.patients:          # more patients left on that doctor's page
            return redirect(back_url)
        return redirect(url_for("admin.doctors") if back_doctor else back_url)
    return render_template("transfer.html", patient=patient, form=form, has_others=bool(others),
                           cancel_url=back_url)
