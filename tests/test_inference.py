"""Tests for the AI pipeline and PDF reports (Phase 5)."""
import io
from pathlib import Path

import numpy as np
import pytest

from app import create_app
from app.config import BASE_DIR, TestConfig
from app.extensions import db
from app.inference import best_scores, draw_findings, summarize
from app.models import Dentist, Patient, XRayImage

REAL_MODEL = BASE_DIR / "models" / "best.pt"
SAMPLE_XRAYS = sorted((BASE_DIR / "data" / "YOLO" / "YOLO" / "test" / "images").glob("*.jpg"))

FINDINGS = [{"label": "Caries", "confidence": 0.61, "box": [10, 10, 30, 30]},
            {"label": "Caries", "confidence": 0.42, "box": [50, 50, 70, 70]},
            {"label": "Impacted tooth", "confidence": 0.93, "box": [5, 40, 40, 90]}]


def test_best_scores_keeps_highest_per_condition():
    assert best_scores(FINDINGS) == {"Caries": 0.61, "Impacted tooth": 0.93}


def test_summary_mentions_found_and_missing_conditions():
    text = summarize(FINDINGS)
    assert "2 possible caries" in text and "61%" in text
    assert "did not detect periapical lesion, bone loss" in text
    assert "did not detect any" in summarize([])


def test_drawing_does_not_change_the_original():
    image = np.zeros((100, 100, 3), np.uint8)
    drawn = draw_findings(image, FINDINGS)
    assert image.sum() == 0 and drawn.sum() > 0


# ---------------------------------------------------------------- full pipeline with the real model

needs_model = pytest.mark.skipif(not REAL_MODEL.exists() or not SAMPLE_XRAYS,
                                 reason="needs models/best.pt and the Kaggle test images")


@pytest.fixture
def client(tmp_path):
    app = create_app(TestConfig)
    app.config.update(UPLOAD_FOLDER=tmp_path, MODEL_PATH=REAL_MODEL)
    with app.app_context():
        db.create_all()
        doctor = Dentist(name="Dr Test", email="doc@example.com")
        doctor.set_password("password123")
        db.session.add_all([doctor, Patient(name="Test Patient", dentist=doctor)])
        db.session.commit()
        client = app.test_client()
        client.post("/login", data={"email": "doc@example.com", "password": "password123"})
        yield client
        db.drop_all()


@needs_model
def test_upload_runs_ai_and_makes_a_report(client):
    response = client.post("/doctor/patients/1", content_type="multipart/form-data", follow_redirects=True,
                           data={"image": (io.BytesIO(SAMPLE_XRAYS[0].read_bytes()), "scan.jpg")})
    assert b"AI analysis finished" in response.data
    xray = XRayImage.query.one()
    assert xray.result is not None and xray.result.model_version.startswith("YOLOv8")
    assert client.get("/doctor/xrays/1/annotated").status_code == 200
    pdf = client.get("/doctor/xrays/1/report")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")


@needs_model
def test_rerun_replaces_the_old_result(client):
    client.post("/doctor/patients/1", content_type="multipart/form-data",
                data={"image": (io.BytesIO(SAMPLE_XRAYS[1].read_bytes()), "scan.jpg")})
    first_date = XRayImage.query.one().result.analysis_date
    client.post("/doctor/xrays/1/analyse")
    db.session.expire_all()                               # read fresh data from the database
    xray = db.session.get(XRayImage, 1)
    assert xray.result.analysis_date > first_date and len(xray.result.reports) == 1


@needs_model
def test_dentist_reviews_a_finding(client):
    # pick a sample the model finds something on
    for sample in SAMPLE_XRAYS[:10]:
        client.post("/doctor/patients/1", content_type="multipart/form-data",
                    data={"image": (io.BytesIO(sample.read_bytes()), "scan.jpg")})
        xray = XRayImage.query.order_by(XRayImage.id.desc()).first()
        if xray.result.findings:
            break
    url = f"/doctor/xrays/{xray.id}/findings/0/review"
    pdf_before = client.get(f"/doctor/xrays/{xray.id}/report").data

    client.post(url, data={"decision": "agree"})
    db.session.expire_all()
    assert xray.result.findings[0]["review"] == "agree"
    assert client.get(f"/doctor/xrays/{xray.id}/report").data != pdf_before     # PDF rebuilt
    assert b"1 agreed" in client.get(f"/doctor/xrays/{xray.id}").data

    client.post(url, data={"decision": "agree"})                                  # same again = clear
    db.session.expire_all()
    assert xray.result.findings[0]["review"] is None

    assert client.post(url, data={"decision": "maybe"}).status_code == 400
    assert client.post(f"/doctor/xrays/{xray.id}/findings/999/review",
                       data={"decision": "agree"}).status_code == 400


def test_missing_model_keeps_the_upload(tmp_path):
    app = create_app(TestConfig)
    app.config["UPLOAD_FOLDER"] = tmp_path
    with app.app_context():
        db.create_all()
        doctor = Dentist(name="Dr Test", email="doc@example.com")
        doctor.set_password("password123")
        db.session.add_all([doctor, Patient(name="P", dentist=doctor)])
        db.session.commit()
        client = app.test_client()
        client.post("/login", data={"email": "doc@example.com", "password": "password123"})
        import cv2
        png = cv2.imencode(".png", np.zeros((20, 20, 3), np.uint8))[1].tobytes()
        response = client.post("/doctor/patients/1", content_type="multipart/form-data", follow_redirects=True,
                               data={"image": (io.BytesIO(png), "scan.png")})
        assert b"model file" in response.data and XRayImage.query.count() == 1
        db.drop_all()
