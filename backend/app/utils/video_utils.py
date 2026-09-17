"""
video_utils.py — Annotation helpers for drawing on frames.
"""

import cv2
import numpy as np
from typing import Optional


def draw_tracked_persons(
    frame: np.ndarray,
    tracked,
    dwell_start: dict = None,
    trails: dict = None,
) -> np.ndarray:
    """Draw bounding boxes + global ID + dwell time + trail for each tracked person."""
    if len(tracked) == 0 or tracked.tracker_id is None:
        return frame

    import time
    now = time.time()
    global_ids = tracked.data.get("global_id", None)

    COLORS = [
        (0,200,80),(0,160,255),(255,100,0),(180,0,255),(0,220,220),
        (255,200,0),(255,60,120),(80,255,160),(255,140,60),(100,100,255),
    ]

    for i, (box, tid) in enumerate(zip(tracked.xyxy, tracked.tracker_id)):
        x1, y1, x2, y2 = map(int, box)
        gid = int(global_ids[i]) if global_ids is not None and i < len(global_ids) else int(tid)
        color = COLORS[gid % len(COLORS)]

        # Draw trail
        if trails and gid in trails and len(trails[gid]) > 1:
            pts = list(trails[gid])
            for j in range(1, len(pts)):
                alpha = j / len(pts)
                c = tuple(int(v * alpha) for v in color)
                cv2.line(frame, pts[j-1], pts[j], c, 2)

        # Bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        # Dwell time
        dwell_sec = round(now - dwell_start[gid], 1) if dwell_start and gid in dwell_start else 0
        label = f"ID:{gid}  {dwell_sec}s" if dwell_sec > 0 else f"ID:{gid}"

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 6, y1), color, -1)
        cv2.putText(frame, label, (x1 + 3, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    return frame


def draw_heatmap_overlay(frame: np.ndarray, heatmap: np.ndarray, alpha: float = 0.4) -> np.ndarray:
    """Blend accumulated heatmap onto frame."""
    if heatmap is None or heatmap.max() == 0:
        return frame
    h, w = frame.shape[:2]
    norm = cv2.resize(heatmap, (w, h))
    norm = np.clip(norm / (norm.max() + 1e-6) * 255, 0, 255).astype(np.uint8)
    colored = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
    # Only show where there's actual heat
    mask = norm > 10
    overlay = frame.copy()
    overlay[mask] = cv2.addWeighted(frame, 1 - alpha, colored, alpha, 0)[mask]
    return overlay


def draw_stats_hud(frame: np.ndarray, stats: dict) -> np.ndarray:
    """Overlay live stats HUD in top-right corner."""
    h, w = frame.shape[:2]
    lines = [
        f"Inside : {stats.get('currently_inside', 0)}",
        f"Unique : {stats.get('total_unique_people', 0)}",
        f"In/Out : {stats.get('entries', 0)}/{stats.get('exits', 0)}",
        f"Dwell  : {stats.get('dwell_avg_sec', 0)}s avg",
    ]
    if stats.get('queue_alert'):
        lines.append("⚠ QUEUE ALERT")

    panel_w, panel_h = 200, len(lines) * 22 + 10
    x0, y0 = w - panel_w - 8, 8
    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x0 + panel_w, y0 + panel_h), (15, 15, 15), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)
    for j, line in enumerate(lines):
        color = (0, 80, 255) if '⚠' in line else (210, 210, 210)
        cv2.putText(frame, line, (x0 + 6, y0 + 18 + j * 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
    return frame


def draw_virtual_line(frame, line_y, color=(0,255,255), thickness=2, label="ENTRY/EXIT"):
    h, w = frame.shape[:2]
    cv2.line(frame, (0, line_y), (w, line_y), color, thickness)
    cv2.putText(frame, label, (10, line_y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    return frame


def draw_zone_overlay(frame, zone_counts, width, height, alpha=0.25, zone_polygons=None):
    colors = [(255,100,100),(100,255,100),(100,100,255),(255,200,50),(180,100,255)]
    if zone_polygons:
        overlay = frame.copy()
        for i, (name, poly) in enumerate(zone_polygons.items()):
            cv2.fillPoly(overlay, [poly], colors[i % len(colors)])
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
        for i, (name, poly) in enumerate(zone_polygons.items()):
            color = colors[i % len(colors)]
            cv2.polylines(frame, [poly], True, color, 2)
            cx, cy = int(poly[:,0].mean()), int(poly[:,1].mean())
            cv2.putText(frame, f"{name}:{zone_counts.get(name,0)}",
                        (cx-30, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    return frame
