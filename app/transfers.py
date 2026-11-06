"""
Transferring patients from one doctor to another.

Used by doctors (their own patients) and by the admin (any patient, or all of
a doctor's patients at once, with or without removing that doctor).
"""
from app.models import ROLE_DOCTOR, Dentist, Report, XRayImage


def other_doctors(excluded_id):
    """All doctors except one, sorted by name: the choices for 'transfer to'."""
    return Dentist.query.filter(Dentist.role == ROLE_DOCTOR, Dentist.id != excluded_id) \
        .order_by(Dentist.name).all()


def doctor_choices(doctors):
    """Options for a dropdown: (id, "Name (email)")."""
    return [(d.id, f"{d.name} ({d.email})") for d in doctors]


def transfer_patient(patient, new_doctor):
    """
    Give one patient to another doctor. Their X-rays and reports move with them,
    because the doctor pages find X-rays through the patient. Who uploaded each
    X-ray stays recorded, so the history remains accurate.
    """
    patient.dentist = new_doctor


def transfer_all_patients(old_doctor, new_doctor):
    """Give every patient of old_doctor to new_doctor. Returns how many moved."""
    patients = list(old_doctor.patients)
    for patient in patients:
        transfer_patient(patient, new_doctor)
    return len(patients)


def hand_over_records(old_doctor, new_doctor):
    """
    Before a doctor is deleted: also re-attribute the X-rays they uploaded and the
    reports they made, so no record points to a doctor who no longer exists.
    """
    XRayImage.query.filter_by(dentist_id=old_doctor.id).update({"dentist_id": new_doctor.id})
    Report.query.filter_by(dentist_id=old_doctor.id).update({"dentist_id": new_doctor.id})
