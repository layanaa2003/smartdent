"""
Connects the AI step to the database: analyse an X-ray, store the result,
and create its PDF report. Called right after an upload, or from "Re-run analysis".
"""
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.inference import analyze_file, annotated_name, model_version
from app.models import AnalysisResult, Report
from app.recommendations import assess_xray
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


def rebuild_report(xray, doctor):
    """Re-create the newest PDF report of an X-ray in place (same file name)."""
    if not xray.result.reports:
        return
    report = max(xray.result.reports, key=lambda r: r.report_date)
    annotated = upload_path(annotated_name(xray.image_path))
    report.summary = assess_xray(xray, upload_path(xray.image_path))["summary"]   # follows the reviews
    build_report_pdf(upload_path(report.file_path), xray.patient, doctor, xray, xray.result,
                     annotated, report.summary)
