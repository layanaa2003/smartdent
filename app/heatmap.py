"""
Heatmap: WHERE on the X-ray the AI model was looking (explainable AI).

Method: EigenCAM (Muhammad & Yeasin, 2020), a gradient-free member of the Grad-CAM family.
Grad-CAM needs the gradient of one class score, which a YOLO detector does not give for a
whole image. EigenCAM instead takes the feature maps the detector passes to its detection
heads and keeps their main pattern (the first principal component). Bright areas are the
parts of the image that drove the model's features most. It needs no extra training.
We use the heads for small and medium objects: lesions are small, and the large-object
head only showed the image border in our tests.

Steps:
  1. Clean the X-ray with ml.preprocess (exactly as for detection) and resize it to the
     size the model was trained at.
  2. Run the model once and record the three feature maps.
  3. For each map: first principal component -> one value per position -> 0..1.
  4. Average the three maps, stretch back to the X-ray size, and colour it over the X-ray
     (red/yellow = most attention, no colour = little attention).

The heatmap explains the model; it is not a diagnosis. It is made on demand the first time
the dentist asks for it, and saved next to the upload as <name>_heatmap.jpg.
"""
import threading
from pathlib import Path

import cv2
import numpy as np

from ml.preprocess import preprocess_image

STRIDE = 32           # YOLOv8 needs image sides that are a multiple of 32
MAX_OPACITY = 0.6     # how strongly the colours cover the X-ray where attention is highest
MIN_SHOWN = 0.25      # attention below 25% of the maximum is not coloured, so the X-ray stays readable

_net = None
_net_path = None
_lock = threading.Lock()   # one heatmap at a time: the recording hooks are set on the shared network


def heatmap_name(image_name):
    """File name of the heatmap of an upload, e.g. abc.jpg -> abc_heatmap.jpg."""
    return f"{Path(image_name).stem}_heatmap.jpg"


def _load_network(model_path):
    """The model's PyTorch network, loaded once (separately from the detection model)."""
    global _net, _net_path
    from ultralytics import YOLO
    if _net is None or _net_path != Path(model_path):
        yolo = YOLO(str(model_path))
        size = int(yolo.ckpt.get("train_args", {}).get("imgsz", 640)) if yolo.ckpt else 640
        net = yolo.model.float().eval()
        for p in net.parameters():
            p.requires_grad_(False)
        _net, _net_path = (net, size), Path(model_path)
    return _net


def _to_tensor(image_bgr, size):
    """Resize (long side = size), pad to a multiple of 32, and make a 1x3xHxW tensor (0..1, RGB)."""
    import torch
    h, w = image_bgr.shape[:2]
    scale = size / max(h, w)
    new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
    resized = cv2.resize(image_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
    pad_w, pad_h = -new_w % STRIDE, -new_h % STRIDE
    padded = cv2.copyMakeBorder(resized, 0, pad_h, 0, pad_w, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    return torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0), (new_w, new_h)


def principal_map(features):
    """
    EigenCAM for one feature map (C x h x w tensor): project every position onto the first
    principal component of the channels. Returns an h x w array scaled to 0..1.
    """
    import torch
    channels = features.shape[0]
    flat = features.reshape(channels, -1).T.double()          # one row per position
    centred = flat - flat.mean(dim=0)
    _, _, vt = torch.linalg.svd(centred, full_matrices=False)
    projection = centred @ vt[0]
    # The sign of a principal component is arbitrary. Point it the same way as the overall
    # activation strength, so "bright" means "strong features", not the opposite.
    strength = flat.sum(dim=1)
    if torch.dot(projection, strength - strength.mean()) < 0:
        projection = -projection
    cam = projection.clamp(min=0).reshape(features.shape[1:]).numpy()
    return cam / cam.max() if cam.max() > 0 else cam


def attention_map(image_bgr, model_path):
    """0..1 attention map with the same height and width as image_bgr (an original X-ray)."""
    import torch
    with _lock:
        net, size = _load_network(model_path)
        tensor, (used_w, used_h) = _to_tensor(preprocess_image(image_bgr), size)
        layers = [net.model[i] for i in net.model[-1].f[:2]]  # inputs of the small + medium object heads
        recorded = []
        hooks = [layer.register_forward_hook(lambda _m, _i, out: recorded.append(out.detach()))
                 for layer in layers]
        try:
            with torch.no_grad():
                net(tensor)
        finally:
            for hook in hooks:
                hook.remove()
    full_h, full_w = tensor.shape[2:]
    maps = [cv2.resize(principal_map(f[0]).astype(np.float32), (full_w, full_h), interpolation=cv2.INTER_LINEAR)
            for f in recorded]
    cam = np.mean(maps, axis=0)[:used_h, :used_w]             # drop the padding
    cam = cv2.resize(cam, (image_bgr.shape[1], image_bgr.shape[0]), interpolation=cv2.INTER_LINEAR)
    cam -= cam.min()
    return cam / cam.max() if cam.max() > 0 else cam


def overlay(image_bgr, cam):
    """Colour the attention map over the X-ray: strong attention = red/yellow, weak = left clear."""
    colours = cv2.applyColorMap(np.uint8(255 * cam), cv2.COLORMAP_JET).astype(np.float32)
    alpha = (MAX_OPACITY * np.clip((cam - MIN_SHOWN) / (1 - MIN_SHOWN), 0, 1))[..., None]
    return np.uint8(image_bgr.astype(np.float32) * (1 - alpha) + colours * alpha)


def make_heatmap(image_path, model_path, out_path=None):
    """Make and save the heatmap of one X-ray file. Returns the path of the saved JPEG."""
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Could not read image {image_path}")
    out_path = Path(out_path or Path(image_path).with_name(heatmap_name(Path(image_path).name)))
    cv2.imwrite(str(out_path), overlay(image, attention_map(image, model_path)), [cv2.IMWRITE_JPEG_QUALITY, 90])
    return out_path
