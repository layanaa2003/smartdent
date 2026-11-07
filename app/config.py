"""
App settings. Secrets are read from environment variables (the .env file),
never written in the code. See .env.example for the list.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent   # the smartdent folder
load_dotenv(BASE_DIR / ".env")                      # copy the .env values into os.environ


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")          # signs login cookies; must be secret
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'smartdent.db'}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False             # not needed, saves memory
    # X-rays are kept outside the public "static" folder, so only logged-in users can see them.
    UPLOAD_FOLDER = Path(os.environ.get("UPLOAD_FOLDER", BASE_DIR / "instance" / "uploads"))
    MODEL_PATH = BASE_DIR / "models" / "best.pt"       # trained YOLO model from Colab
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024              # refuse uploads over 20 MB

    # Email (optional). If SMTP_HOST is empty, the app offers a download instead of sending.
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_SENDER = os.environ.get("SMTP_SENDER", "")

    # Hosted on Hugging Face Spaces (it sets SPACE_ID). The Space page shows the app inside a frame
    # on huggingface.co, so the login cookie must be allowed there, and only over HTTPS.
    HOSTED = bool(os.environ.get("SPACE_ID"))
    if HOSTED:
        SESSION_COOKIE_SAMESITE = "None"
        SESSION_COOKIE_SECURE = True


class TestConfig(Config):
    """Used by the tests: a throw-away database that lives only in memory."""
    TESTING = True
    SECRET_KEY = "test-only-key"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False      # lets tests post forms without a CSRF token
    SMTP_HOST = ""                # never send real email from tests
    MODEL_PATH = BASE_DIR / "tests" / "no-model-here.pt"   # tests that need the model set it themselves
