"""
core/attendance_notifier.py — Sends face recognition events to the attendance API
"""

import os
import uuid
import requests
import logging
from datetime import datetime, timezone

log = logging.getLogger("AttendanceNotifier")

ATTENDANCE_API_URL = os.getenv("ATTENDANCE_API_URL", "http://localhost:8000/api/attendance/ai-event")
AI_SERVICE_API_KEY = os.getenv("AI_SERVICE_API_KEY", "smart-retail-ai-key-2025")

# Map face embedding names → employee_code in DB
NAME_TO_CODE = {
    "Vishal":  "EMP0001",
    "Shubham": "EMP0002",  # update with Shubham's actual employee_code
}


def notify_attendance(employee_code: str, camera_id: str, confidence: float):
    code = NAME_TO_CODE.get(employee_code, employee_code)  # map name → employee_code
    payload = {
        "eventId":    str(uuid.uuid4()),
        "cameraId":   camera_id,
        "employeeId": code,
        "eventType":  "FACE_RECOGNIZED",
        "confidence": round(float(confidence), 4),
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    }
    try:
        resp = requests.post(
            ATTENDANCE_API_URL,
            json=payload,
            headers={"x-ai-service-key": AI_SERVICE_API_KEY},
            timeout=5,
        )
        data = resp.json()
        if data.get("success") and data.get("processed"):
            log.info(f"[ATTENDANCE] {employee_code} → {data.get('attendanceAction')} (camera={camera_id})")
        else:
            log.debug(f"[ATTENDANCE] skipped: {data.get('reason')} (employee={employee_code})")
    except Exception as e:
        log.warning(f"[ATTENDANCE] notify failed for {employee_code}: {e}")
