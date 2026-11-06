"""
Database tables, matching the ER diagram in the report:

  Dentist 1---* Patient 1---* XRayImage 1---1 AnalysisResult 1---* Report

  Dentist        - a user account. role is "admin" or "doctor".
  Patient        - belongs to the doctor who added them.
  XRayImage      - an uploaded panoramic X-ray of a patient.
  AnalysisResult - what the AI found on one X-ray (stored as JSON text).
  Report         - a PDF summary of a result, written for the patient.

Each class is one table; each db.Column is one column.
"""
import json
from datetime import date, datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager

ROLE_ADMIN = "admin"
ROLE_DOCTOR = "doctor"


def utc_now():
    """Current time in UTC, used as the default for date columns."""
    return datetime.now(timezone.utc)


class Dentist(UserMixin, db.Model):
    """A user who can log in: either the admin or a doctor."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(30))
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(10), nullable=False, default=ROLE_DOCTOR)

    patients = db.relationship("Patient", back_populates="dentist")

    def set_password(self, password):
        """Store a one-way hash of the password, never the password itself."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """True if `password` matches the stored hash."""
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == ROLE_ADMIN

    def __repr__(self):
        return f"<Dentist {self.email} ({self.role})>"


class Patient(db.Model):
    """A patient, owned by the doctor who added them."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(30))
    dob = db.Column(db.Date)                                   # date of birth
    dentist_id = db.Column(db.Integer, db.ForeignKey("dentist.id"), nullable=False)

    dentist = db.relationship("Dentist", back_populates="patients")
    # Deleting a patient also deletes their X-rays (and through them, results and reports).
    xrays = db.relationship("XRayImage", back_populates="patient",
                            cascade="all, delete-orphan", order_by="XRayImage.upload_date.desc()")

    @property
    def age(self):
        """Age in whole years, or None if the date of birth is unknown."""
        if not self.dob:
            return None
        today = date.today()
        return today.year - self.dob.year - ((today.month, today.day) < (self.dob.month, self.dob.day))

    def __repr__(self):
        return f"<Patient {self.name}>"


class XRayImage(db.Model):
    """One uploaded X-ray image file (the file itself is on disk, the path is stored here)."""
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    dentist_id = db.Column(db.Integer, db.ForeignKey("dentist.id"), nullable=False)
    upload_date = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    image_path = db.Column(db.String(255), nullable=False)      # relative to app/static/uploads
    image_type = db.Column(db.String(20), nullable=False, default="panoramic")

    patient = db.relationship("Patient", back_populates="xrays")
    dentist = db.relationship("Dentist")
    result = db.relationship("AnalysisResult", back_populates="image", uselist=False,
                             cascade="all, delete-orphan")

    def __repr__(self):
        return f"<XRayImage {self.id} of patient {self.patient_id}>"


class AnalysisResult(db.Model):
    """
    The AI output for one X-ray.
    findings_json holds a list like:
      [{"label": "Caries", "confidence": 0.87, "box": [x1, y1, x2, y2]}, ...]
    confidence_scores holds the highest confidence per condition, e.g. {"Caries": 0.87}.
    """
    id = db.Column(db.Integer, primary_key=True)
    image_id = db.Column(db.Integer, db.ForeignKey("x_ray_image.id"), nullable=False, unique=True)
    findings_json = db.Column(db.Text, nullable=False, default="[]")
    confidence_scores = db.Column(db.Text, nullable=False, default="{}")
    model_version = db.Column(db.String(50), nullable=False)
    analysis_date = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    image = db.relationship("XRayImage", back_populates="result")
    reports = db.relationship("Report", back_populates="result", cascade="all, delete-orphan")

    # SQLite stores text, so these helpers convert to and from Python lists/dicts.
    @property
    def findings(self):
        return json.loads(self.findings_json)

    @findings.setter
    def findings(self, value):
        self.findings_json = json.dumps(value)

    @property
    def scores(self):
        return json.loads(self.confidence_scores)

    @scores.setter
    def scores(self, value):
        self.confidence_scores = json.dumps(value)

    def __repr__(self):
        return f"<AnalysisResult for image {self.image_id}>"


class Report(db.Model):
    """A generated report (PDF file) for one analysis result."""
    id = db.Column(db.Integer, primary_key=True)
    result_id = db.Column(db.Integer, db.ForeignKey("analysis_result.id"), nullable=False)
    dentist_id = db.Column(db.Integer, db.ForeignKey("dentist.id"), nullable=False)
    summary = db.Column(db.Text, nullable=False)
    report_date = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    file_path = db.Column(db.String(255))

    result = db.relationship("AnalysisResult", back_populates="reports")
    dentist = db.relationship("Dentist")

    def __repr__(self):
        return f"<Report {self.id}>"


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login calls this on every request to find the logged-in user."""
    return db.session.get(Dentist, int(user_id))
