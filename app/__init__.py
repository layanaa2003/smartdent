"""
SmartDent web app. create_app() builds and configures the Flask app
(the "application factory" pattern), so tests can build their own copy.
"""
import secrets
from datetime import timezone
from pathlib import Path

from flask import Flask, redirect, render_template, url_for
from flask_login import current_user

from app.config import BASE_DIR, Config
from app.extensions import csrf, db, login_manager


def create_app(config_class=Config):
    app = Flask(__name__, instance_path=str(BASE_DIR / "instance"))
    app.config.from_object(config_class)
    if not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = load_or_create_secret_key(Path(app.instance_path))
    if app.config.get("HOSTED"):
        # Behind Hugging Face's proxy: trust its headers so Flask knows the page is HTTPS.
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app import models  # noqa: F401  (registers the tables with SQLAlchemy)
    register_blueprints(app)
    register_template_helpers(app)
    register_error_pages(app)
    return app


def load_or_create_secret_key(instance_dir):
    """
    No SECRET_KEY in .env: use the random key kept in instance/secret_key,
    making one the first time. So the app runs without any .env file, and
    logins survive a restart. The file stays on this computer only.
    """
    key_file = instance_dir / "secret_key"
    if key_file.exists():
        return key_file.read_text().strip()
    instance_dir.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32)
    key_file.write_text(key)
    return key


def register_blueprints(app):
    """Each blueprint is one part of the site: login, admin pages, doctor pages."""
    from app.admin import bp as admin_bp
    from app.auth import bp as auth_bp
    from app.doctor import bp as doctor_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(doctor_bp, url_prefix="/doctor")

    @app.route("/")
    def index():
        """Visitors see the SmartDent website; logged-in users go to their own dashboard."""
        if not current_user.is_authenticated:
            return render_template("landing.html")
        return redirect(url_for("admin.doctors" if current_user.is_admin else "doctor.dashboard"))


def register_error_pages(app):
    """Friendly pages for "not allowed" and "not found" (the status codes stay 403 / 404)."""
    messages = {403: ("You can't open this page", "This page belongs to a different role."),
                404: ("Page not found", "It may have been removed, or it belongs to another doctor.")}

    def show(error):
        title, text = messages[error.code]
        return render_template("error.html", code=error.code, title=title, text=text), error.code

    for code in messages:
        app.register_error_handler(code, show)


def register_template_helpers(app):
    @app.context_processor
    def finding_colours():
        """The box colour of each finding, so every page uses the same colour key."""
        from app.doctor import FINDING_COLOURS
        return {"finding_colours": FINDING_COLOURS}

    @app.template_filter("datetime")
    def format_datetime(value):
        """Show a stored UTC time in this computer's local time zone."""
        if not value:
            return ""
        if value.tzinfo is None:                  # SQLite forgets the time zone; we always store UTC
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone().strftime("%d %b %Y, %H:%M")

    @app.template_filter("initials")
    def initials(name):
        """'Dr Lina Haddad' -> 'LH', for the round name badges."""
        words = (name or "").replace("Dr ", "").split()
        return "".join(w[0] for w in words[:2]).upper() or "?"

    @app.template_filter("date")
    def format_date(value):
        """Just the day, e.g. 14 Oct 2026."""
        return format_datetime(value)[:11] if value else ""
