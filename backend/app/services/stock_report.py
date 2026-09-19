"""
services/stock_report.py

When ShelfDetector detects EMPTY or LOW STOCK on cam3:
  1. Save annotated screenshot to outputs/stock_reports/
  2. POST report to Node.js backend
"""

import os
import cv2
import logging
import threading
import urllib.request
import urllib.error
import json
from datetime import datetime, timezone, timedelta

from app.config import NODEJS_BACKEND_URL, NODEJS_AI_API_KEY, OUTPUT_DIR

log = logging.getLogger("StockReport")

SCREENSHOT_DIR = os.path.join(OUTPUT_DIR, "stock_reports")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

IST = timezone(timedelta(hours=5, minutes=30))

# Cooldown: don't send duplicate reports within N seconds per camera
_last_report: dict = {}
COOLDOWN_SEC = 120  # 2 minutes


def maybe_report(camera_id: str, shelf_result: dict, annotated_frame):
    """
    Call this after every shelf detection.
    Only triggers if status is EMPTY or LOW STOCK and cooldown has passed.
    Runs in a background thread — non-blocking.
    """
    status = shelf_result.get("status", "NORMAL")
    if status not in ("EMPTY", "LOW STOCK"):
        return

    now = datetime.now(IST).timestamp()
    last = _last_report.get(camera_id, 0)
    if now - last < COOLDOWN_SEC:
        return

    _last_report[camera_id] = now

    # Copy frame before passing to thread (avoid mutation)
    frame_copy = annotated_frame.copy() if annotated_frame is not None else None

    threading.Thread(
        target=_run,
        args=(camera_id, shelf_result, frame_copy),
        daemon=True,
    ).start()


def _run(camera_id: str, shelf_result: dict, frame):
    try:
        now_ist   = datetime.now(IST)
        ts_str    = now_ist.strftime("%Y%m%d_%H%M%S")
        date_str  = now_ist.strftime("%Y-%m-%d")
        time_str  = now_ist.strftime("%H:%M:%S")

        # ── 1. Save screenshot ────────────────────────────────────────────────
        screenshot_path = None
        if frame is not None:
            filename       = f"{camera_id}_{ts_str}.jpg"
            screenshot_path = os.path.join(SCREENSHOT_DIR, filename)
            cv2.imwrite(screenshot_path, frame)
            log.info(f"[StockReport] Screenshot saved: {screenshot_path}")

        # ── 2. Build payload ──────────────────────────────────────────────────
        payload = {
            "cameraId":       camera_id,
            "status":         shelf_result.get("status"),
            "occupancy":      shelf_result.get("occupancy", 0),
            "outOfStock":     shelf_result.get("out_of_stock", 0),
            "emptyZones":     shelf_result.get("empty_zones", 0),
            "reducedZones":   shelf_result.get("reduced_zones", 0),
            "labelCounts":    shelf_result.get("label_counts", {}),
            "screenshotPath": screenshot_path or "",
            "detectedAt":     now_ist.isoformat(),
            "date":           date_str,
            "time":           time_str,
        }

        # ── 3. POST to Node.js ────────────────────────────────────────────────
        url  = f"{NODEJS_BACKEND_URL}/api/stock-reports"
        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type":    "application/json",
                "x-ai-service-key": NODEJS_AI_API_KEY,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            log.info(f"[StockReport] Sent to Node.js: {resp.status} — {camera_id} {shelf_result.get('status')}")

    except Exception as e:
        log.warning(f"[StockReport] Failed: {e}")
