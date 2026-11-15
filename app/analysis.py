"""
Connects the AI step to the database: analyse an X-ray, store the result,
and create its PDF report. Called right after an upload, or from "Re-run analysis".
"""
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.inference import analyze_file, annotated_name, model_version
from app.models import AnalysisResult, DentistFinding, Report
from app.recommendations import assess_xray, image_size
from app.reports import build_report_pdf
from app.storage import upload_path


def remove_old_result(xray):
    """Delete a previous result (and its report files) before re-analysing."""
    if xray.result is None:
        return
    for report in xray.result.reports:
        if report.file_path:
            upload_path(report.file_path).unlink(missing_ok=True)
    db.session.delete(xray.result)
    db.session.flush()


def run_analysis(xray, doctor):
    """
    Analyse one X-ray and save everything. Returns the seconds the AI step took.
    Raises app.inference.ModelNotFound if models/best.pt is missing.
    """
    model_path = current_app.config["MODEL_PATH"]
    findings, scores, summary, annotated_path, seconds = analyze_file(upload_path(xray.image_path), model_path)

    remove_old_result(xray)
    result = AnalysisResult(image=xray, model_version=model_version(model_path))
    result.findings, result.scores = findings, scores
    db.session.add(result)
    db.session.flush()
    summary = assess_xray(xray, upload_path(xray.image_path))["summary"]   # written for this X-ray

    pdf_name = f"report_{xray.id}_{datetime.now(timezone.utc):%Y%m%d%H%M%S}.pdf"
    build_report_pdf(upload_path(pdf_name), xray.patient, doctor, xray, result, annotated_path, summary)
    db.session.add(Report(result=result, dentist_id=doctor.id, summary=summary, file_path=pdf_name))
    db.session.commit()
    return seconds


REVIEW_CHOICES = ("agree", "disagree")


def set_review(xray, index, decision, doctor):
    """
    Record the dentist's opinion of one AI finding ("agree" or "disagree").
    Choosing the same answer again clears it. The PDF report is rebuilt so it
    always shows the latest reviews. Returns the new value (or None).
    """
    findings = xray.result.findings          # a copy: JSON text -> Python list
    current = findings[index].get("review")
    findings[index]["review"] = None if decision == current else decision
    xray.result.findings = findings          # write the whole list back as JSON
    rebuild_report(xray, doctor)
    db.session.commit()
    return findings[index]["review"]


def review_counts(findings):
    """How many findings were agreed with, disagreed with, or not reviewed yet."""
    counts = {"agree": 0, "disagree": 0, None: 0}
    for f in findings:
        counts[f.get("review")] += 1
    return counts


MIN_BOX_SIZE = 4        # pixels; smaller boxes are almost certainly a stray click


class BadBox(ValueError):
    """The box drawn by the dentist is outside the image or too small."""


def clean_box(box, width, height):
    """
    Put x1,y1 at the top left, keep the box inside the image, and refuse tiny boxes.
    Returns [x1, y1, x2, y2] or raises BadBox.
    """
    x1, x2 = sorted((box[0], box[2]))
    y1, y2 = sorted((box[1], box[3]))
    if width and height:
        x1, x2 = max(0, min(x1, width)), max(0, min(x2, width))
        y1, y2 = max(0, min(y1, height)), max(0, min(y2, height))
    if x2 - x1 < MIN_BOX_SIZE or y2 - y1 < MIN_BOX_SIZE:
        raise BadBox("Draw a box around the area on the X-ray first.")
    return [x1, y1, x2, y2]


def add_dentist_finding(xray, doctor, label, box, note=""):
    """
    Save a finding the dentist marked by hand (something the AI missed), then
    rebuild the PDF report so it includes it. Raises BadBox for an unusable box.
    """
    x1, y1, x2, y2 = clean_box(box, *image_size(upload_path(xray.image_path)))
    finding = DentistFinding(image=xray, dentist_id=doctor.id, label=label,
                             x1=x1, y1=y1, x2=x2, y2=y2, note=(note or "").strip() or None)
    db.session.add(finding)
    db.session.flush()
    if xray.result is not None:
        rebuild_report(xray, doctor)
    db.session.commit()
    return finding


def remove_dentist_finding(xray, finding, doctor):
    """Delete one dentist-added finding and rebuild the report."""
    xray.dentist_findings.remove(finding)        # delete-orphan removes the row
    db.session.flush()
    if xray.result is not None:
        rebuild_report(xray, doctor)
    db.session.commit()


def rebuild_report(xray, doctor):
    """Re-create the newest PDF report of an X-ray in place (same file name)."""
    if not xray.result.reports:
        return
    report = max(xray.result.reports, key=lambda r: r.report_date)
    annotated = upload_path(annotated_name(xray.image_path))
    report.summary = assess_xray(xray, upload_path(xray.image_path))["summary"]   # follows the reviews
    build_report_pdf(upload_path(report.file_path), xray.patient, doctor, xray, xray.result,
                     annotated, report.summary)
