"""
app/services/pg_sync.py
Posts AI analytics data to Node.js which writes to PostgreSQL.
SQLite remains as silent local backup.
"""
import threading
import logging
import json
from urllib.request import urlopen, Request
from urllib.error import URLError

from app.config import NODEJS_BACKEND_URL, NODEJS_AI_API_KEY

log = logging.getLogger("pg_sync")

_HEADERS = {
    "Content-Type": "application/json",
    "x-ai-service-key": NODEJS_AI_API_KEY,
}


def _post(path: str, payload: dict):
    """Fire-and-forget POST to Node.js. Never raises."""
    def _run():
        try:
            data = json.dumps(payload).encode()
            req  = Request(f"{NODEJS_BACKEND_URL}{path}", data=data, headers=_HEADERS, method="POST")
            with urlopen(req, timeout=5):
                pass
        except URLError:
            pass  # Node.js offline — SQLite backup still has the data
        except Exception as e:
            log.debug(f"pg_sync {path} failed: {e}")
    threading.Thread(target=_run, daemon=True).start()


def sync_footfall(camera_id: str, store_id: str, log_date: str,
                  entries: int, exits: int, currently_inside: int, total_unique: int):
    _post("/api/ai-ingest/footfall", {
        "camera_id": camera_id, "store_id": store_id, "log_date": log_date,
        "entries": entries, "exits": exits,
        "currently_inside": currently_inside, "total_unique": total_unique,
    })


def sync_movement(global_id: int, camera_id: str, camera_name: str,
                  event_type: str, zone: str, bbox: list, store_id: str):
    _post("/api/ai-ingest/movement", {
        "global_id": global_id, "camera_id": camera_id, "camera_name": camera_name,
        "event_type": event_type, "zone": zone, "store_id": store_id,
        "bbox_x1": bbox[0] if bbox else None, "bbox_y1": bbox[1] if bbox else None,
        "bbox_x2": bbox[2] if bbox else None, "bbox_y2": bbox[3] if bbox else None,
    })


def sync_alert(alert_type: str, severity: str, camera_id: str, zone: str,
               global_id: int, message: str, extra_data: dict, store_id: str):
    _post("/api/ai-ingest/alert", {
        "alert_type": alert_type, "severity": severity, "camera_id": camera_id,
        "zone": zone, "global_id": global_id, "message": message,
        "extra_data": extra_data, "store_id": store_id,
    })


def sync_journey(global_id: int, journey: list, total_dwell_sec: float,
                 zones_visited: int, entry_time: str, exit_time: str, store_id: str):
    _post("/api/ai-ingest/journey", {
        "global_id": global_id, "journey": journey,
        "total_dwell_sec": total_dwell_sec, "zones_visited": zones_visited,
        "entry_time": entry_time, "exit_time": exit_time, "store_id": store_id,
    })


def sync_face_attendance(name: str, attendance_date: str, first_seen_time: str,
                         similarity: float, camera_id: str, store_id: str):
    # 1. Simple face log (upsert — no duplicate per day)
    _post("/api/ai-ingest/face-attendance", {
        "name": name, "attendance_date": attendance_date,
        "first_seen_time": first_seen_time, "similarity": similarity,
        "camera_id": camera_id, "store_id": store_id,
    })
    # 2. Proper attendance — check-in/out session + employee_attendance table
    import uuid
    _post("/api/attendance/ai-event", {
        "eventId":    str(uuid.uuid4()),
        "cameraId":   camera_id,
        "employeeId": name,          # employee_code = name enrolled in face DB
        "eventType":  "FACE_RECOGNIZED",
        "confidence": round(float(similarity), 4),
        "timestamp":  first_seen_time,
    })
