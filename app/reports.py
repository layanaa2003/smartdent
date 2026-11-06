"""
The PDF report for one analysed X-ray, made with ReportLab.

It contains the patient and doctor details, the annotated X-ray, a table of
findings with confidence scores, the summary written for this X-ray, suggested
next steps for the dentist, and the advisory disclaimer.
"""
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DISCLAIMER = "AI output is advisory only; the dentist makes the final diagnosis."
PAGE_WIDTH = A4[0] - 4 * cm          # usable width inside the 2 cm margins


def details_table(patient, doctor, xray, result):
    """The small key/value table at the top of the report."""
    rows = [
        ["Patient", patient.name],
        ["Date of birth", patient.dob.strftime("%d %b %Y") if patient.dob else "Not given"],
        ["Dentist", doctor.name],
        ["X-ray uploaded", xray.upload_date.strftime("%d %b %Y")],
        ["Analysed with", result.model_version],
    ]
    table = Table(rows, colWidths=[4 * cm, PAGE_WIDTH - 4 * cm])
    table.setStyle(TableStyle([("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return table


REVIEW_WORDS = {"agree": "Agrees", "disagree": "Disagrees", None: "Not reviewed"}


def findings_table(findings):
    """One row per finding: condition, AI confidence and the dentist's review."""
    rows = [["#", "Condition", "AI confidence", "Dentist review"]]
    rows += [[str(i), f["label"], f"{f['confidence']:.0%}", REVIEW_WORDS[f.get("review")]]
             for i, f in enumerate(findings, 1)]
    table = Table(rows, colWidths=[1.2 * cm, 6.5 * cm, 3.5 * cm, 3.8 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d9e2ec")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def review_line(findings):
    """One sentence summing up the dentist's review, e.g. 'Dentist review: 2 agreed, 1 disagreed'."""
    agreed = sum(f.get("review") == "agree" for f in findings)
    disagreed = sum(f.get("review") == "disagree" for f in findings)
    pending = len(findings) - agreed - disagreed
    text = f"Dentist review: {agreed} agreed, {disagreed} disagreed"
    return text + (f", {pending} not reviewed yet." if pending else ".")


def scaled_image(path, max_width=PAGE_WIDTH, max_height=11 * cm):
    """The X-ray, shrunk to fit the page while keeping its proportions."""
    image = Image(str(path))
    ratio = min(max_width / image.imageWidth, max_height / image.imageHeight)
    image.drawWidth, image.drawHeight = image.imageWidth * ratio, image.imageHeight * ratio
    return image


def next_steps_section(xray, styles):
    """'Suggested next steps for the dentist', from app/recommendations.py (rejected findings left out)."""
    from app.recommendations import assess_xray
    from app.storage import upload_path
    assessment = assess_xray(xray, upload_path(xray.image_path))
    if not assessment or not assessment["steps"]:
        return []
    parts = [Paragraph("Suggested next steps for the dentist", styles["Heading2"]),
             Paragraph("Based on published guidelines. Confirm every finding clinically first; "
                       "treatment is your decision.", styles["Italic"]), Spacer(1, 0.2 * cm)]
    for step in assessment["steps"]:
        title = f"<b>{step['label']}</b> ({step['areas']})"
        if step["low"]:
            title += " - low confidence, look again first"
        parts += [Paragraph(title, styles["Normal"]),
                  Paragraph(f"Check: {step['check']}", styles["Normal"]),
                  Paragraph(f"Consider: {step['consider']}", styles["Normal"])]
        if step["note"]:
            parts.append(Paragraph(f"Age: {step['note']}", styles["Normal"]))
        parts += [Paragraph(f"<font size=8 color='grey'>Source: {step['source']}</font>", styles["Normal"]),
                  Spacer(1, 0.25 * cm)]
    return parts


def build_report_pdf(pdf_path, patient, doctor, xray, result, annotated_path, summary):
    """Write the PDF to pdf_path."""
    styles = getSampleStyleSheet()
    findings = result.findings
    story = [
        Paragraph("SmartDent X-ray report", styles["Title"]),
        Paragraph(f"Generated {datetime.now():%d %b %Y, %H:%M}", styles["Normal"]),
        Spacer(1, 0.4 * cm),
        details_table(patient, doctor, xray, result),
        Spacer(1, 0.4 * cm),
        scaled_image(annotated_path),
        Spacer(1, 0.4 * cm),
        Paragraph("Findings", styles["Heading2"]),
        findings_table(findings) if findings else Paragraph("No findings detected.", styles["Normal"]),
        Spacer(1, 0.2 * cm),
        Paragraph(review_line(findings), styles["Normal"]) if findings else Spacer(1, 0),
        Spacer(1, 0.3 * cm),
        Paragraph("Summary for this X-ray", styles["Heading2"]),
        Paragraph(summary, styles["Normal"]),
        Spacer(1, 0.3 * cm),
        *next_steps_section(xray, styles),
        Spacer(1, 0.6 * cm),
        Paragraph(f"<b>{DISCLAIMER}</b>", styles["Normal"]),
    ]
    SimpleDocTemplate(str(pdf_path), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                      topMargin=2 * cm, bottomMargin=2 * cm, title="SmartDent X-ray report").build(story)
    return Path(pdf_path)
