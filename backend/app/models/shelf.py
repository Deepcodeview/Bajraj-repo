"""
shelf.py — Dual-model + CV fallback shelf detector for CAM-3.

Strategy:
  1. Run best.pt       (space_na / space_a)       imgsz=640
  2. Run empty_best.pt (Empty-Space / Reduced)     imgsz=1280
  3. Run out_of_stock.pt                           imgsz=640
  4. If all models give NO detections → CV fallback
"""

import cv2
import numpy as np
from ultralytics import YOLO


_THRESHOLD_NORMAL    = 0.70
_THRESHOLD_LOW_STOCK = 0.40

# Shelf ROI: left 55% width, top 85% height (where shelves are in CAM-3)
_ROI_W = 0.55
_ROI_H = 0.85

# CV fallback thresholds
_CV_EDGE_NORMAL    = 0.045
_CV_EDGE_LOW       = 0.025
_CV_TEXTURE_NORMAL = 45.0
_CV_TEXTURE_LOW    = 25.0

# ── Per-class colors (BGR) ────────────────────────────────────────────────────
_CLASS_COLORS = {
    # Model 1: occupied products — distinct greens/teals per product
    'space_na':      (34,  197,  94),   # bright green
    'milk':          (0,   210, 210),   # cyan
    'bread':         (0,   165, 255),   # orange
    'butter':        (0,   255, 255),   # yellow
    'yogurt':        (180, 255,  80),   # lime
    'chips':         (255, 180,   0),   # sky blue
    'pasta':         (200, 100, 255),   # purple
    'whipped_cream': (255, 255, 200),   # light yellow
    'ice_cream':     (255, 200, 150),   # light blue
    'spread':        (100, 255, 150),   # mint
    'miscellaneous': (150, 150, 255),   # lavender
    'dairy_product': (0,   200, 180),   # teal
    'canned_item':   (50,  200, 255),   # gold
    'juice':         (0,   100, 255),   # deep orange
    'sour_cream':    (200, 255, 200),   # pale green
    'pet_food':      (100, 200,  50),   # olive green
    # Model 1: empty slot — red
    'space_a':       (0,     0, 220),
    # Model 2: zone-level
    'Empty-Space':   (0,     0, 255),   # red
    'Reduced':       (0,   140, 255),   # orange
    # Model 3: out_of_stock.pt — actual class names
    'non-empty':     (34,  197,  94),   # green  — product present
    'reducing':      (0,   140, 255),   # orange — stock reducing
    'empty':         (30,   30, 220),   # red    — out of stock
    # legacy fallback
    'out_of_stock':  (30,   30, 220),
    'Out_of_Stock':  (30,   30, 220),
    'OOS':           (30,   30, 220),
}

# Legend shown on frame (top-right corner)
_LEGEND_ITEMS = [
    ('non-empty  (Stocked)',    (34,  197,  94)),   # green
    ('reducing   (Low Stock)',  (0,   140, 255)),   # orange
    ('empty      (Out of Stock)',(30,  30, 220)),   # red
    ('Empty-Space (Zone Empty)',(0,     0, 255)),   # red zone
]


def _class_color(label: str) -> tuple:
    return _CLASS_COLORS.get(label, (180, 180, 180))


def draw_shelf_legend(frame: np.ndarray):
    """Draw color legend in top-right corner."""
    h, w = frame.shape[:2]
    x0, y0 = w - 260, 10
    row_h, pad = 22, 6
    box_h = pad * 2 + row_h * len(_LEGEND_ITEMS)
    cv2.rectangle(frame, (x0 - pad, y0 - pad), (w - 4, y0 + box_h), (15, 15, 15), -1)
    cv2.rectangle(frame, (x0 - pad, y0 - pad), (w - 4, y0 + box_h), (70, 70, 70), 1)
    for i, (name, color) in enumerate(_LEGEND_ITEMS):
        y = y0 + i * row_h
        cv2.rectangle(frame, (x0, y + 3), (x0 + 16, y + 16), color, -1)
        cv2.putText(frame, name, (x0 + 22, y + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (220, 220, 220), 1, cv2.LINE_AA)


def draw_shelf_overlay(frame: np.ndarray, shelf_result: dict):
    """
    Full shelf visualization on frame:
      - Colored bounding boxes with rounded corners effect
      - Label pill with confidence
      - Bottom status banner with occupancy bar
      - Top-right legend
      - Top-left stats panel (OOS / Empty / Reduced counts)
    """
    h_f, w_f = frame.shape[:2]
    boxes        = shelf_result.get("boxes", [])
    status       = shelf_result.get("status", "")
    occupancy    = shelf_result.get("occupancy", 0.0)
    oos          = shelf_result.get("out_of_stock", 0)
    empty_z      = shelf_result.get("empty_zones", 0)
    reduced_z    = shelf_result.get("reduced_zones", 0)
    occupied     = shelf_result.get("occupied", 0)
    occ_pct      = int(occupancy * 100)

    # ── 1. Bounding boxes + label pills ──────────────────────────────────────
    for (x1, y1, x2, y2, lbl, cf, col) in boxes:
        # Semi-transparent fill
        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), col, -1)
        cv2.addWeighted(overlay, 0.12, frame, 0.88, 0, frame)
        # Border — thick
        cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)
        # Corner accents (L-shaped corners for clean look)
        clen = min(12, (x2 - x1) // 3, (y2 - y1) // 3)
        for cx, cy, dx, dy in [(x1,y1,1,1),(x2,y1,-1,1),(x1,y2,1,-1),(x2,y2,-1,-1)]:
            cv2.line(frame, (cx, cy), (cx + dx*clen, cy), col, 3)
            cv2.line(frame, (cx, cy), (cx, cy + dy*clen), col, 3)
        # Label pill
        txt = f"{lbl}  {cf:.0%}"
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
        pill_x1, pill_y1 = x1, max(0, y1 - th - 10)
        pill_x2, pill_y2 = x1 + tw + 10, y1
        cv2.rectangle(frame, (pill_x1, pill_y1), (pill_x2, pill_y2), col, -1)
        # White text on pill
        cv2.putText(frame, txt, (pill_x1 + 5, pill_y2 - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

    # ── 2. Bottom status banner ───────────────────────────────────────────────
    banner_h = 72
    bc = (30, 160, 30) if status == "NORMAL" else (20, 130, 220) if status == "LOW STOCK" else (30, 30, 200)
    # Semi-transparent banner
    overlay2 = frame.copy()
    cv2.rectangle(overlay2, (0, h_f - banner_h), (w_f, h_f), (10, 10, 10), -1)
    cv2.addWeighted(overlay2, 0.75, frame, 0.25, 0, frame)

    # Status icon + text
    icon = "[OK]" if status == "NORMAL" else "[!!]" if status == "LOW STOCK" else "[XX]"
    cv2.putText(frame, f"{icon} SHELF: {status}",
                (12, h_f - banner_h + 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, bc, 2, cv2.LINE_AA)

    # Occupancy bar
    bar_x, bar_y = 12, h_f - banner_h + 36
    bar_w, bar_h = min(300, w_f - 24), 14
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (60, 60, 60), -1)
    fill_w = int(bar_w * occupancy)
    bar_color = (30,200,30) if occ_pct >= 70 else (30,165,220) if occ_pct >= 40 else (30,30,220)
    if fill_w > 0:
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h), bar_color, -1)
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (100, 100, 100), 1)
    cv2.putText(frame, f"Occupancy: {occ_pct}%",
                (bar_x + bar_w + 8, bar_y + 11),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 200, 200), 1, cv2.LINE_AA)

    # Stats: Stocked / OOS / Empty / Reduced
    stats = [
        (f"Stocked: {occupied}",  (30, 200, 30)),
        (f"OOS: {oos}",           (30,  30, 220)),
        (f"Empty: {empty_z}",     (30,  30, 255)),
        (f"Reduced: {reduced_z}", (30, 140, 255)),
    ]
    sx = bar_x
    for txt_s, col_s in stats:
        (sw, _), _ = cv2.getTextSize(txt_s, cv2.FONT_HERSHEY_SIMPLEX, 0.44, 1)
        cv2.putText(frame, txt_s, (sx, h_f - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, col_s, 1, cv2.LINE_AA)
        sx += sw + 18

    # ── 3. Top-right legend ───────────────────────────────────────────────────
    draw_shelf_legend(frame)


def _cv_shelf_status(frame) -> dict:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
    h, w = gray.shape
    roi  = gray[:int(h * _ROI_H), :int(w * _ROI_W)]

    brightness   = float(roi.mean())
    texture_std  = float(roi.std())
    edges        = cv2.Canny(roi, 30, 80)
    edge_density = float(edges.sum()) / (roi.shape[0] * roi.shape[1] * 255)

    if edge_density >= _CV_EDGE_NORMAL and texture_std >= _CV_TEXTURE_NORMAL:
        status = "NORMAL"
    elif edge_density >= _CV_EDGE_LOW or texture_std >= _CV_TEXTURE_LOW:
        status = "LOW STOCK"
    else:
        status = "EMPTY"

    occupancy = round(min(edge_density / 0.06, 1.0), 3)
    return {
        "status":        status,
        "occupied":      0,
        "available":     0,
        "occupancy":     occupancy,
        "empty_zones":   0,
        "reduced_zones": 0,
        "out_of_stock":  0,
        "confidence":    round(edge_density, 4),
        "method":        "cv_fallback",
        "cv_brightness": round(brightness, 1),
        "cv_texture":    round(texture_std, 1),
        "cv_edges":      round(edge_density, 4),
        "label_counts":  {},
    }


class ShelfDetector:
    def __init__(self, slot_model: YOLO = None, empty_model: YOLO = None, out_of_stock_model: YOLO = None):
        self.slot_model         = slot_model
        self.empty_model        = empty_model
        self.out_of_stock_model = out_of_stock_model

    def detect(self, frame) -> dict:
        occupied = available = empty_zones = reduced_zones = out_of_stock_count = 0
        confs         = []
        model_fired   = False
        boxes_to_draw = []   # [(x1,y1,x2,y2,label,conf,color)]
        label_counts: dict[str, int] = {}   # sent to frontend for legend

        EMPTY_LABELS    = {'space_a'}
        OCCUPIED_LABELS = {'space_na', 'milk', 'bread', 'butter', 'yogurt', 'chips',
                           'pasta', 'whipped_cream', 'ice_cream', 'spread', 'miscellaneous',
                           'dairy_product', 'canned_item', 'juice', 'sour_cream', 'pet_food'}

        h_f, w_f  = frame.shape[:2]
        roi_x_max = int(w_f * _ROI_W)
        roi_y_max = int(h_f * _ROI_H)

        # ── Model 1: product-level (best.pt) ─────────────────────────────────
        if self.slot_model is not None:
            try:
                r1 = self.slot_model(frame, conf=0.25, imgsz=640, verbose=False, device="cpu")[0]
                if r1.boxes and len(r1.boxes) > 0:
                    for cls, conf, box in zip(r1.boxes.cls, r1.boxes.conf, r1.boxes.xyxy):
                        cx = float((box[0] + box[2]) / 2)
                        cy = float((box[1] + box[3]) / 2)
                        if cx > roi_x_max or cy > roi_y_max:
                            continue
                        label = r1.names[int(cls)]
                        color = _class_color(label)
                        confs.append(float(conf))
                        label_counts[label] = label_counts.get(label, 0) + 1
                        if label in OCCUPIED_LABELS:
                            occupied += 1
                        elif label in EMPTY_LABELS:
                            available += 1
                        else:
                            occupied += 1
                        boxes_to_draw.append((int(box[0]), int(box[1]), int(box[2]), int(box[3]),
                                              label, float(conf), color))
                    if occupied + available > 0:
                        model_fired = True
            except Exception:
                pass

        # ── Model 2: zone-level (empty_best.pt) ──────────────────────────────
        if self.empty_model is not None:
            try:
                r2 = self.empty_model(frame, conf=0.25, imgsz=1280, verbose=False, device="cpu")[0]
                if r2.boxes and len(r2.boxes) > 0:
                    for cls, conf, box in zip(r2.boxes.cls, r2.boxes.conf, r2.boxes.xyxy):
                        cx = float((box[0] + box[2]) / 2)
                        cy = float((box[1] + box[3]) / 2)
                        if cx > roi_x_max or cy > roi_y_max:
                            continue
                        label = r2.names[int(cls)]
                        color = _class_color(label)
                        confs.append(float(conf))
                        label_counts[label] = label_counts.get(label, 0) + 1
                        if label == "Empty-Space":
                            empty_zones += 1
                        elif label == "Reduced":
                            reduced_zones += 1
                        boxes_to_draw.append((int(box[0]), int(box[1]), int(box[2]), int(box[3]),
                                              label, float(conf), color))
                    if empty_zones + reduced_zones > 0:
                        model_fired = True
            except Exception:
                pass

        # ── Model 3: out_of_stock.pt ──────────────────────────────────────────
        # Classes: non-empty=stocked(green), reducing=low(orange), empty=OOS(red)
        if self.out_of_stock_model is not None:
            try:
                r3 = self.out_of_stock_model(frame, conf=0.25, imgsz=640, verbose=False, device="cpu")[0]
                if r3.boxes and len(r3.boxes) > 0:
                    for cls, conf, box in zip(r3.boxes.cls, r3.boxes.conf, r3.boxes.xyxy):
                        cx = float((box[0] + box[2]) / 2)
                        cy = float((box[1] + box[3]) / 2)
                        if cx > roi_x_max or cy > roi_y_max:
                            continue
                        label = r3.names[int(cls)]
                        color = _class_color(label)
                        confs.append(float(conf))
                        label_counts[label] = label_counts.get(label, 0) + 1
                        if label == 'non-empty':
                            occupied += 1
                        elif label == 'reducing':
                            reduced_zones += 1
                            out_of_stock_count += 1
                        else:  # empty
                            out_of_stock_count += 1
                        boxes_to_draw.append((int(box[0]), int(box[1]), int(box[2]), int(box[3]),
                                              label, float(conf), color))
                    if len(r3.boxes) > 0:
                        model_fired = True
            except Exception:
                pass

        # ── CV Fallback ───────────────────────────────────────────────────────
        if not model_fired:
            return _cv_shelf_status(frame)

        # ── Fuse results ──────────────────────────────────────────────────────
        total    = occupied + available
        avg_conf = round(sum(confs) / len(confs), 3) if confs else 0.0

        if total == 0:
            slot_status = "NO SHELF DETECTED"
        else:
            occ_ratio = occupied / total
            if occ_ratio >= _THRESHOLD_NORMAL:
                slot_status = "NORMAL"
            elif occ_ratio >= _THRESHOLD_LOW_STOCK:
                slot_status = "LOW STOCK"
            else:
                slot_status = "EMPTY"

        if empty_zones >= 3 or out_of_stock_count >= 3:
            empty_status = "EMPTY"
        elif empty_zones >= 1 or reduced_zones >= 1 or out_of_stock_count >= 1:
            empty_status = "LOW STOCK"
        else:
            empty_status = slot_status

        if slot_status == "NO SHELF DETECTED" and empty_zones == 0 and reduced_zones == 0 and out_of_stock_count == 0:
            return {**_cv_shelf_status(frame), "method": "cv_fallback_no_model_detections"}

        _rank = {"EMPTY": 0, "LOW STOCK": 1, "NORMAL": 2, "NO SHELF DETECTED": 3}
        final = min(slot_status, empty_status, key=lambda s: _rank.get(s, 3))

        return {
            "status":        final,
            "occupied":      occupied,
            "available":     available,
            "occupancy":     round(occupied / total, 3) if total > 0 else round(1.0 - min(out_of_stock_count / 5, 1.0), 3),
            "empty_zones":   empty_zones,
            "reduced_zones": reduced_zones,
            "out_of_stock":  out_of_stock_count,
            "confidence":    avg_conf,
            "method":        "model",
            "boxes":         boxes_to_draw,
            "label_counts":  label_counts,
        }
