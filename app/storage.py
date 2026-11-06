"""
Saving uploaded X-ray files safely.

* The file must really be an image (we try to decode it, not just trust the name).
* It gets a random name, so the original file name (which may contain a
  patient's name) is never stored, and two uploads can't overwrite each other.
"""
import uuid
from pathlib import Path

import cv2
import numpy as np
from flask import current_app


class InvalidImage(ValueError):
    """Raised when an uploaded file is not a readable JPEG/PNG image."""


def is_readable_image(data):
    """True if OpenCV can decode the bytes as an image."""
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    return image is not None


def save_upload(file_storage):
    """Check and save an uploaded file. Returns the new file name (relative to UPLOAD_FOLDER)."""
    data = file_storage.read()
    if not data or not is_readable_image(data):
        raise InvalidImage("The file is not a valid JPEG or PNG image.")
    extension = Path(file_storage.filename).suffix.lower()
    if extension == ".jpeg":
        extension = ".jpg"
    name = f"{uuid.uuid4().hex}{extension}"
    folder = Path(current_app.config["UPLOAD_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)
    return name


def upload_path(name):
    """Full path of a stored upload."""
    return Path(current_app.config["UPLOAD_FOLDER"]) / name
