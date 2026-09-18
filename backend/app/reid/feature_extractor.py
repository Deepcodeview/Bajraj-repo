"""
reid/feature_extractor.py — Lightweight Re-ID feature extractor.
"""

import cv2
import numpy as np

_model = None
_transform = None


def _load_model():
    global _model, _transform
    if _model is not None:
        return

    import torch
    import torchvision.models as models
    import torchvision.transforms as T

    backbone = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V1)
    backbone.classifier = torch.nn.Identity()
    backbone.eval()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    _model = backbone.to(device)
    _model._device = device

    _transform = T.Compose([
        T.ToPILImage(),
        T.Resize((128, 64)),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])


def extract(frame: np.ndarray, box) -> np.ndarray:
    _load_model()

    import torch

    x1, y1, x2, y2 = map(int, box)
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)

    if x2 - x1 < 10 or y2 - y1 < 20:
        return np.zeros(1280, dtype=np.float32)

    crop = frame[y1:y2, x1:x2]
    crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)

    try:
        tensor = _transform(crop_rgb).unsqueeze(0).to(_model._device)
        with torch.no_grad():
            feat = _model(tensor).squeeze().cpu().numpy()
        norm = np.linalg.norm(feat)
        return feat / (norm + 1e-6)
    except Exception:
        return np.zeros(1280, dtype=np.float32)
