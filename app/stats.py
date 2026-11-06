"""
The summary numbers shown at the top of the admin and doctor dashboards.
"""
from datetime import datetime, timedelta, timezone

from ml import CLASS_NAMES
from app.models import ROLE_DOCTOR, AnalysisResult, Dentist, Patient, XRayImage

RECENT_DAYS = 30


def since_recent():
    """The start of the 'recent' period (the last 30 days)."""
    return datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)


def findings_by_condition(results):
    """How many X-rays had each condition flagged, e.g. {"Caries": 4, ...}."""
    counts = {name: 0 for name in CLASS_NAMES}
    for result in results:
        for name in result.scores:
            counts[name] = counts.get(name, 0) + 1
    return counts


def doctor_stats(doctor_id):
    """Numbers for one doctor's dashboard."""
    xrays = XRayImage.query.join(Patient).filter(Patient.dentist_id == doctor_id)
    results = AnalysisResult.query.join(XRayImage).join(Patient).filter(Patient.dentist_id == doctor_id).all()
    return {
        "patients": Patient.query.filter_by(dentist_id=doctor_id).count(),
        "xrays": xrays.count(),
        "xrays_recent": xrays.filter(XRayImage.upload_date >= since_recent()).count(),
        "analysed": len(results),
        "by_condition": findings_by_condition(results),
    }


def admin_stats():
    """Numbers for the admin dashboard (the whole clinic)."""
    results = AnalysisResult.query.all()
    return {
        "doctors": Dentist.query.filter_by(role=ROLE_DOCTOR).count(),
        "patients": Patient.query.count(),
        "xrays": XRayImage.query.count(),
        "xrays_recent": XRayImage.query.filter(XRayImage.upload_date >= since_recent()).count(),
        "analysed": len(results),
        "by_condition": findings_by_condition(results),
    }


def xrays_to_review(doctor_id, limit=6):
    """
    A doctor's newest X-rays that still need them: not analysed yet, or with AI
    findings the dentist has not agreed or disagreed with.
    """
    xrays = (XRayImage.query.join(Patient).filter(Patient.dentist_id == doctor_id)
             .order_by(XRayImage.upload_date.desc()).all())
    waiting = [x for x in xrays
               if x.result is None or any(f.get("review") is None for f in x.result.findings)]
    return waiting[:limit], len(waiting)
