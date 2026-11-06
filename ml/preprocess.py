"""
Image preprocessing used BOTH for training (Colab) and for the web app (Phase 5).
Using the exact same function in both places means the model always sees
images that look the way it was trained on.

Steps:
  1. Grayscale    - X-rays have no colour, so we drop the (identical) colour channels.
  2. Noise        - a small median filter removes speckle noise but keeps edges sharp.
  3. Contrast     - CLAHE evens out brightness, so dark and bright X-rays look alike
                    (a form of normalization).
  4. Back to 3 channels, because YOLO expects colour-shaped input.

Resizing to 640 px and scaling pixels to 0-1 are done by YOLO itself (imgsz=640).
"""
import cv2

MEDIAN_KERNEL = 3          # size of the noise filter (must be odd)
CLAHE_CLIP_LIMIT = 2.0     # how strongly contrast is boosted
CLAHE_TILE_GRID = (8, 8)   # the image is split into 8x8 tiles for local contrast


def preprocess_image(image_bgr):
    """Take an OpenCV BGR image and return the cleaned BGR image."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    denoised = cv2.medianBlur(gray, MEDIAN_KERNEL)
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_GRID)
    contrasted = clahe.apply(denoised)
    return cv2.cvtColor(contrasted, cv2.COLOR_GRAY2BGR)


def preprocess_file(src_path, dst_path):
    """Read an image file, preprocess it and save it. Returns False if it can't be read."""
    image = cv2.imread(str(src_path))
    if image is None:
        return False
    cv2.imwrite(str(dst_path), preprocess_image(image))
    return True
