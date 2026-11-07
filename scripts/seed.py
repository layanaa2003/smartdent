"""
Create the database tables and the first accounts.

Run from the smartdent folder:

    python scripts/seed.py          # first admin only (email/name from .env, password asked)
    python scripts/seed.py --demo   # demo accounts for trying SmartDent (used by start.bat / start.sh)

--demo only adds data when the database has no accounts yet, so it never
touches a database that is already in use. The demo logins are:

    Administrator  admin@smartdent.local   / SmartDent-admin-2026
    Dentist        doctor@smartdent.local  / SmartDent-doctor-2026

plus one fictional patient (Demo Patient) belonging to the demo dentist.
On a public copy (e.g. Hugging Face), set DEMO_ADMIN_PASSWORD and DEMO_DOCTOR_PASSWORD
to use other passwords than these published ones.

Without --demo, the admin's email and name come from .env (ADMIN_EMAIL, ADMIN_NAME).
The password comes from ADMIN_PASSWORD in .env if set, otherwise you are asked
to type it (it is not shown on screen). Only a hash of it is stored.
Running the script again is safe: it never creates a second admin.
"""
import getpass
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so "import app" works

from app import create_app                                   # noqa: E402
from app.extensions import db                                # noqa: E402
from app.models import ROLE_ADMIN, ROLE_DOCTOR, Dentist, Patient  # noqa: E402

MIN_PASSWORD_LENGTH = 8

# Fixed demo logins, also listed in README.md. Only for a fresh demo database.
DEMO_ADMIN = {"name": "Demo Administrator", "email": "admin@smartdent.local",
              "password": os.environ.get("DEMO_ADMIN_PASSWORD") or "SmartDent-admin-2026"}
DEMO_DOCTOR = {"name": "Dr Demo Dentist", "email": "doctor@smartdent.local",
               "password": os.environ.get("DEMO_DOCTOR_PASSWORD") or "SmartDent-doctor-2026", "phone": "+44 20 7946 0000"}
DEMO_PATIENT = {"name": "Demo Patient", "email": "patient@example.com",
                "phone": "+44 20 7946 0001", "dob": date(1985, 4, 12)}


def ask_password():
    """Read the admin password from .env, or ask for it twice."""
    password = os.environ.get("ADMIN_PASSWORD")
    if password:
        return password
    while True:
        password = getpass.getpass("Choose an admin password: ")
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
        elif password != getpass.getpass("Type it again: "):
            print("The two passwords don't match.")
        else:
            return password


def create_admin(email, name, password):
    """Add the admin account unless an admin already exists. Returns the admin."""
    existing = Dentist.query.filter_by(role=ROLE_ADMIN).first()
    if existing:
        print(f"An admin already exists: {existing.email}. Nothing changed.")
        return existing
    admin = Dentist(name=name, email=email.lower(), role=ROLE_ADMIN)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    print(f"Admin account created: {admin.email}")
    return admin


def create_demo_data():
    """Add the demo admin, dentist and patient, but only to an empty database. Returns True if added."""
    if Dentist.query.first() is not None:
        print("The database already has accounts, so no demo data was added.")
        return False
    create_admin(DEMO_ADMIN["email"], DEMO_ADMIN["name"], DEMO_ADMIN["password"])
    doctor = Dentist(name=DEMO_DOCTOR["name"], email=DEMO_DOCTOR["email"],
                     phone=DEMO_DOCTOR["phone"], role=ROLE_DOCTOR)
    doctor.set_password(DEMO_DOCTOR["password"])
    db.session.add(doctor)
    db.session.add(Patient(dentist=doctor, **DEMO_PATIENT))
    db.session.commit()
    print("Demo data added:")
    for role, account, variable in (("Administrator", DEMO_ADMIN, "DEMO_ADMIN_PASSWORD"),
                                    ("Dentist", DEMO_DOCTOR, "DEMO_DOCTOR_PASSWORD")):
        # A password chosen through the environment is secret, so it is never printed.
        shown = f"(from {variable})" if os.environ.get(variable) else account["password"]
        print(f"  {role:<14} {account['email']:<24} password: {shown}")
    return True


def main():
    app = create_app()
    Path(app.instance_path).mkdir(exist_ok=True)     # folder that holds smartdent.db
    with app.app_context():
        db.create_all()                              # creates any missing tables
        print("Database ready:", app.config["SQLALCHEMY_DATABASE_URI"])
        if "--demo" in sys.argv[1:]:
            create_demo_data()
            return
        email = os.environ.get("ADMIN_EMAIL", "admin@smartdent.local")
        name = os.environ.get("ADMIN_NAME", "Administrator")
        if Dentist.query.filter_by(role=ROLE_ADMIN).first() is None:
            create_admin(email, name, ask_password())
        else:
            create_admin(email, name, password=None)  # just prints who the admin is


if __name__ == "__main__":
    main()
