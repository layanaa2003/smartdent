"""
Login, logout and the role check used on every protected page.
"""
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.forms import LoginForm
from app.models import Dentist

bp = Blueprint("auth", __name__)


def role_required(role):
    """
    Decorator for a page that only one role may open, e.g. @role_required("admin").
    Not logged in -> login page. Logged in with the wrong role -> 403 Forbidden.
    """
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role != role:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = Dentist.query.filter_by(email=form.email.data.strip().lower()).first()
        # Same message for "no such user" and "wrong password", so attackers can't guess emails.
        if user is None or not user.check_password(form.password.data):
            flash("Wrong email or password.", "error")
        else:
            login_user(user)
            return redirect(url_for("index"))
    return render_template("login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
