"""Tests for the database tables (Phase 3). Each test gets a fresh in-memory database."""
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import ROLE_ADMIN, AnalysisResult, Dentist, Patient, Report, XRayImage
from scripts.seed import create_admin


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def make_doctor(email="doc@example.com"):
    doctor = Dentist(name="Dr Test", email=email)
    doctor.set_password("password123")
    db.session.add(doctor)
    db.session.commit()
    return doctor


def make_patient_with_result(doctor):
    """A patient with one X-ray, one AI result and one report."""
    patient = Patient(name="Test Patient", dob=date(1990, 5, 1), dentist=doctor)
    xray = XRayImage(patient=patient, dentist=doctor, image_path="test.jpg")
    result = AnalysisResult(image=xray, model_version="yolov8s-v1")
    result.findings = [{"label": "Caries", "confidence": 0.9, "box": [1, 2, 3, 4]}]
    report = Report(result=result, dentist=doctor, summary="One possible caries.")
    db.session.add_all([patient, xray, result, report])
    db.session.commit()
    return patient


def test_password_is_hashed(app):
    doctor = make_doctor()
    assert doctor.password_hash != "password123"
    assert doctor.check_password("password123")
    assert not doctor.check_password("wrong")
    assert doctor.role == "doctor" and not doctor.is_admin


def test_email_must_be_unique(app):
    make_doctor()
    with pytest.raises(IntegrityError):
        make_doctor()


def test_relationships_follow_the_er_diagram(app):
    doctor = make_doctor()
    patient = make_patient_with_result(doctor)
    xray = patient.xrays[0]
    assert doctor.patients == [patient]
    assert xray.result.findings[0]["label"] == "Caries"
    assert xray.result.reports[0].summary == "One possible caries."
    assert patient.age is not None


def test_deleting_a_patient_deletes_their_xrays_results_and_reports(app):
    patient = make_patient_with_result(make_doctor())
    db.session.delete(patient)
    db.session.commit()
    assert XRayImage.query.count() == AnalysisResult.query.count() == Report.query.count() == 0


def test_seed_creates_only_one_admin(app):
    create_admin("Admin@Example.com", "Admin", "password123")
    create_admin("other@example.com", "Other", "password123")
    admins = Dentist.query.filter_by(role=ROLE_ADMIN).all()
    assert len(admins) == 1 and admins[0].email == "admin@example.com"
    assert admins[0].is_admin
