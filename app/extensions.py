"""
Shared Flask extensions. They are created here, without an app, and connected
to the app later in create_app(). This avoids circular imports.
"""
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()               # the database (SQLite)
login_manager = LoginManager()  # remembers who is logged in
csrf = CSRFProtect()            # blocks forged form submissions from other websites

login_manager.login_view = "auth.login"                  # where to send users who aren't logged in
login_manager.login_message = "Please log in to continue."
