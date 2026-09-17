"""
utils/geometry.py — Bounding box geometry helpers
"""
import numpy as np


def iou(a: list, b: list) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
    return inter / union if union > 0 else 0.0


def center(box: list) -> tuple:
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def box_area(box: list) -> float:
    x1, y1, x2, y2 = box
    return max(0, x2 - x1) * max(0, y2 - y1)


def nms(boxes: list, scores: list, iou_thresh: float) -> list:
    """Non-Maximum Suppression — returns kept indices."""
    if not boxes:
        return []
    boxes  = np.array(boxes,  dtype=float)
    scores = np.array(scores, dtype=float)
    order  = scores.argsort()[::-1]
    kept   = []
    while len(order):
        i = order[0]
        kept.append(int(i))
        if len(order) == 1:
            break
        rest = order[1:]
        ious = np.array([iou(boxes[i], boxes[j]) for j in rest])
        order = rest[ious < iou_thresh]
    return kept
