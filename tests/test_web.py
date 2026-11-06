"""Tests for login, role checks and both dashboards (Phase 4)."""
import io

import cv2
import numpy as np
import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import ROLE_ADMIN, Dentist, Patient, XRayImage

PASSWORD = "password123"


@pytest.fixture
def app(tmp_path):
    app = create_app(TestConfig)
    app.config["UPLOAD_FOLDER"] = tmp_path          # uploads go to a temporary folder
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def make_user(email, role="doctor", name="User"):
    user = Dentist(name=name, email=email, role=role)
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


def make_patient(doctor, name="Pat Example", email=None):
    patient = Patient(name=name, email=email, dentist_id=doctor.id)
    db.session.add(patient)
    db.session.commit()
    return patient


def login(client, email):
    return client.post("/login", data={"email": email, "password": PASSWORD}, follow_redirects=True)


def png_bytes():
    """A tiny real PNG image."""
    ok, encoded = cv2.imencode(".png", np.zeros((10, 10, 3), np.uint8))
    return encoded.tobytes()


# ---------------------------------------------------------------- login

def test_login_sends_each_role_to_its_dashboard(client):
    make_user("admin@example.com", role=ROLE_ADMIN)
    make_user("doc@example.com")
    assert b"Doctors" in login(client, "admin@example.com").data
    client.post("/logout")
    assert b"My patients" in login(client, "doc@example.com").data


def test_wrong_password_is_rejected(client):
    make_user("doc@example.com")
    response = client.post("/login", data={"email": "doc@example.com", "password": "nope"})
    assert b"Wrong email or password" in response.data


def test_visitors_see_the_website_with_a_login_link(client):
    page = client.get("/").data
    assert b"Book an X-Ray Review" in page and b'href="/login"' in page


def test_logged_in_users_skip_the_website(client):
    make_user("doc@example.com")
    login(client, "doc@example.com")
    response = client.get("/")
    assert response.status_code == 302 and "/doctor/" in response.location


def test_pages_need_login(client):
    for url in ["/admin/doctors", "/admin/patients", "/doctor/"]:
        response = client.get(url)
        assert response.status_code == 302 and "/login" in response.location


def test_roles_cannot_open_each_others_pages(client):
    make_user("admin@example.com", role=ROLE_ADMIN)
    make_user("doc@example.com")
    login(client, "doc@example.com")
    assert client.get("/admin/doctors").status_code == 403
    client.post("/logout")
    login(client, "admin@example.com")
    assert client.get("/doctor/").status_code == 403


# ---------------------------------------------------------------- admin

def test_admin_adds_edits_and_removes_a_doctor(client):
    make_user("admin@example.com", role=ROLE_ADMIN)
    login(client, "admin@example.com")
    client.post("/admin/doctors/new", data={"name": "Dr New", "email": "new@example.com",
                                            "password": PASSWORD})
    doctor = Dentist.query.filter_by(email="new@example.com").one()
    client.post(f"/admin/doctors/{doctor.id}/edit", data={"name": "Dr Renamed", "email": "new@example.com"})
    assert db.session.get(Dentist, doctor.id).name == "Dr Renamed"
    assert db.session.get(Dentist, doctor.id).check_password(PASSWORD)   # empty password = unchanged
    client.post(f"/admin/doctors/{doctor.id}/delete")
    assert db.session.get(Dentist, doctor.id) is None


def test_duplicate_doctor_email_is_refused(client):
    make_user("admin@example.com", role=ROLE_ADMIN)
    make_user("doc@example.com")
    login(client, "admin@example.com")
    response = client.post("/admin/doctors/new", data={"name": "X", "email": "doc@example.com",
                                                       "password": PASSWORD})
    assert b"already used" in response.data


def test_doctor_with_patients_must_be_reassigned_before_removal(client):
    make_user("admin@example.com", role=ROLE_ADMIN)
    leaving = make_user("leaving@example.com", name="Dr Leaving")
    staying = make_user("staying@example.com", name="Dr Staying")
    patient = make_patient(leaving)
    login(client, "admin@example.com")

    response = client.post(f"/admin/doctors/{leaving.id}/delete")
    assert "/reassign" in response.location                       # blocked, sent to reassign page
    assert db.session.get(Dentist, leaving.id) is not None

    client.post(f"/admin/doctors/{leaving.id}/reassign", data={"new_doctor": staying.id, "remove_doctor": "y"})
    assert db.session.get(Dentist, leaving.id) is None
    assert db.session.get(Patient, patient.id).dentist_id == staying.id


# ---------------------------------------------------------------- transfers

def test_admin_moves_all_patients_and_keeps_the_doctor(client):
    make_user("admin@example.com", role=ROLE_ADMIN)
    on_leave = make_user("leave@example.com", name="Dr Leave")
    cover = make_user("cover@example.com", name="Dr Cover")
    patients = [make_patient(on_leave, name=f"P{i}") for i in range(3)]
    login(client, "admin@example.com")
    client.post(f"/admin/doctors/{on_leave.id}/reassign", data={"new_doctor": cover.id})
    assert db.session.get(Dentist, on_leave.id) is not None                    # doctor kept
    assert all(db.session.get(Patient, p.id).dentist_id == cover.id for p in patients)


def test_admin_transfers_one_patient(client):
    make_user("admin@example.com", role=ROLE_ADMIN)
    a, b = make_user("a@example.com"), make_user("b@example.com")
    moving, staying = make_patient(a, name="Moving"), make_patient(a, name="Staying")
    login(client, "admin@example.com")
    client.post(f"/admin/patients/{moving.id}/transfer", data={"new_doctor": b.id})
    assert db.session.get(Patient, moving.id).dentist_id == b.id
    assert db.session.get(Patient, staying.id).dentist_id == a.id


def test_admin_transfers_one_patient_from_the_doctors_page(client):
    make_user("admin@example.com", role=ROLE_ADMIN)
    a, b = make_user("a@example.com", name="Dr A"), make_user("b@example.com")
    first, second = make_patient(a, name="First Patient"), make_patient(a, name="Second Patient")
    login(client, "admin@example.com")
    page = client.get(f"/admin/doctors/{a.id}/reassign").data
    assert b"One patient at a time" in page and b"First Patient" in page and b"Second Patient" in page
    response = client.post(f"/admin/patients/{first.id}/transfer?back={a.id}", data={"new_doctor": b.id})
    assert response.location.endswith(f"/admin/doctors/{a.id}/reassign")      # back to Dr A's page
    assert db.session.get(Patient, first.id).dentist_id == b.id
    assert db.session.get(Patient, second.id).dentist_id == a.id


def test_doctor_transfers_own_patient_with_xrays(client):
    me, colleague = make_user("doc@example.com"), make_user("other@example.com")
    patient = make_patient(me)
    login(client, "doc@example.com")
    client.post(f"/doctor/patients/{patient.id}", content_type="multipart/form-data",
                data={"image": (io.BytesIO(png_bytes()), "scan.png")})
    response = client.post(f"/doctor/patients/{patient.id}/transfer", data={"new_doctor": colleague.id},
                           follow_redirects=True)
    assert b"has been transferred" in response.data
    assert db.session.get(Patient, patient.id).dentist_id == colleague.id
    assert client.get(f"/doctor/patients/{patient.id}").status_code == 404     # I lost access
    client.post("/logout")
    login(client, "other@example.com")
    xray = XRayImage.query.one()
    assert client.get(f"/doctor/xrays/{xray.id}").status_code == 200           # X-ray moved too


def test_doctor_cannot_transfer_someone_elses_patient(client):
    other = make_user("other@example.com")
    their_patient = make_patient(other)
    me = make_user("doc@example.com")
    login(client, "doc@example.com")
    response = client.post(f"/doctor/patients/{their_patient.id}/transfer", data={"new_doctor": me.id})
    assert response.status_code == 404
    assert db.session.get(Patient, their_patient.id).dentist_id == other.id


def test_doctor_cannot_transfer_to_an_admin(client):
    admin = make_user("admin@example.com", role=ROLE_ADMIN)
    me, colleague = make_user("doc@example.com"), make_user("other@example.com")
    patient = make_patient(me)
    login(client, "doc@example.com")
    client.post(f"/doctor/patients/{patient.id}/transfer", data={"new_doctor": admin.id})
    assert db.session.get(Patient, patient.id).dentist_id == me.id             # invalid choice refused


def test_admin_sees_all_patients(client):
    make_user("admin@example.com", role=ROLE_ADMIN)
    make_patient(make_user("a@example.com"), name="Alice Patient")
    make_patient(make_user("b@example.com"), name="Bob Patient")
    login(client, "admin@example.com")
    page = client.get("/admin/patients").data
    assert b"Alice Patient" in page and b"Bob Patient" in page


# ---------------------------------------------------------------- doctor

def test_doctor_adds_patient_and_uploads_xray(client):
    make_user("doc@example.com")
    login(client, "doc@example.com")
    client.post("/doctor/patients/new", data={"name": "New Patient", "dob": "1990-01-31"})
    patient = Patient.query.filter_by(name="New Patient").one()

    response = client.post(f"/doctor/patients/{patient.id}", content_type="multipart/form-data",
                           data={"image": (io.BytesIO(png_bytes()), "scan.png")}, follow_redirects=True)
    assert b"X-ray uploaded" in response.data
    xray = XRayImage.query.one()
    assert xray.image_path.endswith(".png") and "scan" not in xray.image_path   # random file name
    assert client.get(f"/doctor/xrays/{xray.id}/image").status_code == 200
    assert b"New Patient" in client.get(f"/doctor/patients/{patient.id}").data   # history page


def test_fake_image_is_rejected(client):
    doctor = make_user("doc@example.com")
    patient = make_patient(doctor)
    login(client, "doc@example.com")
    response = client.post(f"/doctor/patients/{patient.id}", content_type="multipart/form-data",
                           data={"image": (io.BytesIO(b"not really an image"), "fake.png")})
    assert b"not a valid JPEG or PNG" in response.data
    assert XRayImage.query.count() == 0


def test_wrong_file_type_is_rejected(client):
    doctor = make_user("doc@example.com")
    patient = make_patient(doctor)
    login(client, "doc@example.com")
    response = client.post(f"/doctor/patients/{patient.id}", content_type="multipart/form-data",
                           data={"image": (io.BytesIO(b"%PDF"), "report.pdf")})
    assert b"Only JPEG or PNG" in response.data


def test_doctor_cannot_open_another_doctors_patient(client):
    other_patient = make_patient(make_user("other@example.com"))
    make_user("doc@example.com")
    login(client, "doc@example.com")
    assert client.get(f"/doctor/patients/{other_patient.id}").status_code == 404


def test_send_without_email_setup_offers_download(client):
    doctor = make_user("doc@example.com")
    patient = make_patient(doctor, email="patient@example.com")
    login(client, "doc@example.com")
    client.post(f"/doctor/patients/{patient.id}", content_type="multipart/form-data",
                data={"image": (io.BytesIO(png_bytes()), "scan.png")})
    xray = XRayImage.query.one()
    response = client.post(f"/doctor/xrays/{xray.id}/send", follow_redirects=True)
    assert b"Email is not set up" in response.data
    download = client.get(f"/doctor/xrays/{xray.id}/download")
    assert download.status_code == 200 and "attachment" in download.headers["Content-Disposition"]


# ---------------------------------------------------------------- dashboard and error pages

def test_dashboard_lists_xrays_waiting_for_review(client):
    from app.models import AnalysisResult
    doctor = make_user("doc@example.com")
    patient = make_patient(doctor, name="Queue Patient")
    waiting = XRayImage(patient=patient, dentist_id=doctor.id, image_path="a.png")
    done = XRayImage(patient=patient, dentist_id=doctor.id, image_path="b.png")
    db.session.add_all([waiting, done])
    db.session.commit()
    db.session.add(AnalysisResult(image=done, model_version="test",
                                  findings=[{"label": "Caries", "confidence": 0.9, "box": [1, 1, 5, 5], "review": "agree"}]))
    db.session.commit()

    page = login(client, "doc@example.com").data
    assert b"Needs your review" in page and b"1 X-ray waiting for your review" in page
    assert f"/doctor/xrays/{waiting.id}".encode() in page
    assert f'href="/doctor/xrays/{done.id}"'.encode() not in page      # already reviewed


def test_error_pages_are_friendly_and_keep_status(client):
    make_user("doc@example.com")
    login(client, "doc@example.com")
    missing = client.get("/doctor/patients/999")
    assert missing.status_code == 404 and b"Page not found" in missing.data
    forbidden = client.get("/admin/doctors")
    assert forbidden.status_code == 403 and b"open this page" in forbidden.data


def test_analysis_page_shows_summary_and_next_steps(client, app):
    from app.models import AnalysisResult
    doctor = make_user("doc@example.com")
    patient = make_patient(doctor, name="Step Patient")
    (app.config["UPLOAD_FOLDER"] / "a.png").write_bytes(png_bytes())
    xray = XRayImage(patient=patient, dentist_id=doctor.id, image_path="a.png")
    db.session.add(xray)
    db.session.commit()
    db.session.add(AnalysisResult(image=xray, model_version="test", findings=[
        {"label": "Caries", "confidence": 0.9, "box": [1, 1, 4, 4], "review": None},
        {"label": "Bone Loss", "confidence": 0.6, "box": [5, 5, 9, 9], "review": "disagree"}]))
    db.session.commit()
    login(client, "doc@example.com")
    page = client.get(f"/doctor/xrays/{xray.id}").data
    assert b"Summary for this X-ray" in page and b"Suggested next steps" in page
    assert b"bitewing" in page and b"1 finding you rejected is left out" in page
