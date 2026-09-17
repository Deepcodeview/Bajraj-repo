"""
app/routers/face.py — Face Recognition endpoints for smartstore
Endpoints:
  POST /face/recognize        — image → recognition result
  POST /face/enroll           — upload images + re-enroll person
  DELETE /face/persons/{name} — remove person
  GET  /face/persons          — list enrolled persons
  GET  /face/events           — attendance/visitor log
  POST /face/session/reset    — reset session
  GET  /face/health           — status
"""
import os
import cv2
import shutil
import subprocess
import sys
import numpy as np
from datetime import datetime
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Depends
from sqlalchemy.orm import Session

from app.face.config import DATA_DIR, EMBEDDINGS_FILE
from app.database.db import get_db
from app.database.models import AttendanceLog
from app.reid.name_anchor import name_anchor
from app.reid.face_body_fusion import face_body_fusion

router = APIRouter(prefix="/face", tags=["face"])

# Lazy-load recognizer (insightface loads slowly)
_recognizer = None

def _get_recognizer():
    global _recognizer
    if _recognizer is None:
        from app.face.recognizer import FaceRecognizer
        _recognizer = FaceRecognizer()
    return _recognizer


@router.get("/health")
def face_health():
    r = _get_recognizer()
    return {
        "status":   "ok",
        "persons":  len(r.db_names),
        "enrolled": r.db_names,
        "embeddings_file": os.path.exists(EMBEDDINGS_FILE),
    }


@router.post("/recognize")
async def face_recognize(
    file: UploadFile = File(...),
    camera_id: str = "cam6",
    tracked_boxes: str = "",   # JSON string: [[x1,y1,x2,y2], ...]
    global_ids: str = "",      # JSON string: [1, 2, 3, ...]
    db: Session = Depends(get_db)
):
    """Upload image/frame → face recognition + body tracker fusion."""
    import json
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")
    nparr = np.frombuffer(raw, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(400, "Invalid image")

    r = _get_recognizer()
    _, results = r.process_frame(frame)

    today = datetime.now().strftime("%Y-%m-%d")

    # Parse body tracker data if provided
    t_boxes = json.loads(tracked_boxes) if tracked_boxes else []
    g_ids   = json.loads(global_ids)   if global_ids   else []

    for face in results:
        if not face.get("confirmed") or face["name"] in ("Unknown", "voting"):
            continue

        name = face["name"]
        sim  = face.get("sim", 0.0)

        # Face bbox ko body tracker se match karo
        matched_gid = None
        if t_boxes and g_ids:
            matched_gid = face_body_fusion.match_face_to_track(
                face["bbox"], t_boxes, g_ids
            )

        if matched_gid is not None:
            # Body tracker ke global_id ke saath naam anchor karo
            face_body_fusion.confirm_identity(matched_gid, name, sim)
            name_anchor.set_name(matched_gid, name, confidence=sim, camera_id=camera_id)

        # Us din ke liye ek baar DB mein save karo
        already = db.query(AttendanceLog).filter(
            AttendanceLog.name == name,
            AttendanceLog.attendance_date == today,
        ).first()
        if not already:
            db.add(AttendanceLog(
                name=name,
                type="employee",
                attendance_date=today,
                first_seen_time=datetime.now(),
                similarity=sim,
                camera_id=camera_id,
            ))
            db.commit()

    # Har tracked person ka naam fusion se lo (face na dikhe tab bhi)
    enriched = []
    for gid in g_ids:
        fused_name = face_body_fusion.get_name(gid) or name_anchor.get_name(gid)
        enriched.append({"global_id": gid, "name": fused_name or "Unknown"})

    return {
        "faces":        results,
        "face_count":   len(results),
        "tracked":      enriched,
        "timestamp":    datetime.now().isoformat(),
    }


@router.post("/enroll")
async def face_enroll(
    name:  str              = Form(...),
    files: list[UploadFile] = File(...),
):
    """Upload images for a person and rebuild embeddings."""
    person_dir = os.path.join(DATA_DIR, name)
    os.makedirs(person_dir, exist_ok=True)

    saved = 0
    for f in files:
        raw = await f.read()
        if not raw:
            continue
        ext  = os.path.splitext(f.filename or "")[1] or ".jpg"
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:20]
        path = os.path.join(person_dir, f"{ts}{ext}")
        with open(path, "wb") as fp:
            fp.write(raw)
        saved += 1

    if saved == 0:
        raise HTTPException(400, "No valid images uploaded")

    # Re-run enroll script
    enroll_script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "Face_Detection", "enroll.py"
    )
    if os.path.exists(enroll_script):
        subprocess.run([sys.executable, enroll_script],
                       cwd=os.path.dirname(enroll_script), capture_output=True)

    _get_recognizer().reload()

    return {
        "ok":           True,
        "name":         name,
        "images_saved": saved,
        "enrolled":     _get_recognizer().db_names,
    }


@router.delete("/persons/{name}")
def face_delete_person(name: str):
    person_dir = os.path.join(DATA_DIR, name)
    if not os.path.exists(person_dir):
        raise HTTPException(404, f"{name} not found")
    shutil.rmtree(person_dir)

    enroll_script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "Face_Detection", "enroll.py"
    )
    if os.path.exists(enroll_script):
        subprocess.run([sys.executable, enroll_script],
                       cwd=os.path.dirname(enroll_script), capture_output=True)

    _get_recognizer().reload()
    return {"ok": True, "deleted": name, "enrolled": _get_recognizer().db_names}


@router.get("/phone-usage")
def face_phone_usage():
    from app.reid.name_anchor import name_anchor
    rows = name_anchor.get_phone_usage()
    return {"usage": rows, "total_employees": len(rows)}


@router.get("/persons")
def face_list_persons():
    persons = []
    if os.path.exists(DATA_DIR):
        for p in sorted(os.listdir(DATA_DIR)):
            d = os.path.join(DATA_DIR, p)
            if os.path.isdir(d):
                count = len([f for f in os.listdir(d)
                             if f.lower().endswith(('.jpg','.jpeg','.png'))])
                persons.append({"name": p, "images": count})
    return {"persons": persons, "total": len(persons)}


@router.get("/attendance")
def face_attendance(store_id: str = "store_1", date: str = None, db: Session = Depends(get_db)):
    """Get attendance logs — ek din mein ek baar present mark hota hai."""
    query = db.query(AttendanceLog).filter(AttendanceLog.store_id == store_id)
    if date:
        query = query.filter(AttendanceLog.attendance_date == date)
    logs = query.order_by(AttendanceLog.attendance_date.desc()).all()
    return {
        "attendance": [
            {
                "id":           l.id,
                "name":         l.name,
                "type":         l.type,
                "date":         l.attendance_date,
                "first_seen":   l.first_seen_time.strftime("%H:%M:%S") if l.first_seen_time else None,
                "similarity":   l.similarity,
                "camera_id":    l.camera_id,
            }
            for l in logs
        ],
        "total": len(logs),
    }


@router.get("/live-status")
def face_live_status(db: Session = Depends(get_db)):
    """Kaun abhi andar hai — real-time employee status."""
    from datetime import datetime, date
    from app.reid.employee_db import employee_db
    from app.reid.name_anchor import name_anchor

    now       = datetime.now()
    today_str = date.today().isoformat()

    # Attendance DB se aaj ke records
    today_logs = db.query(AttendanceLog).filter(
        AttendanceLog.attendance_date == today_str
    ).all()
    attendance_map = {l.name: l for l in today_logs}

    # employee_db se live profiles
    profiles = employee_db.get_status()

    # name_anchor se currently active
    anchored = name_anchor.get_all()
    active_names = {
        v["name"] for v in anchored.values()
        if v["name"] != "Unknown" and v.get("age_sec", 9999) < 60
    }

    result = []
    for p in profiles:
        name      = p["name"]
        log       = attendance_map.get(name)
        is_active = name in active_names
        last_cam  = p["last_camera"]
        last_sec  = p["last_seen_sec"]

        result.append({
            "name":          name,
            "status":        "active" if is_active else ("present" if log else "absent"),
            "first_seen":    log.first_seen_time.strftime("%H:%M:%S") if log else None,
            "last_seen_sec": last_sec,
            "last_camera":   last_cam,
            "confidence":    p["confidence"],
            "face_confirmed":p["face_confirmed"],
            "sightings":     p["sightings"],
        })

    # Enrolled persons jo aaj nahi aaye
    enrolled = []
    if os.path.exists(DATA_DIR):
        enrolled = [p for p in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, p))]
    for name in enrolled:
        if not any(r["name"] == name for r in result):
            result.append({
                "name":          name,
                "status":        "absent",
                "first_seen":    None,
                "last_seen_sec": None,
                "last_camera":   None,
                "confidence":    0.0,
                "face_confirmed":False,
                "sightings":     0,
            })

    present = sum(1 for r in result if r["status"] in ("active", "present"))
    active  = sum(1 for r in result if r["status"] == "active")

    return {
        "timestamp":     now.strftime("%H:%M:%S"),
        "date":          today_str,
        "total_enrolled":len(result),
        "present_today": present,
        "active_now":    active,
        "absent":        len(result) - present,
        "employees":     result,
    }


@router.get("/events")
def face_events():
    r = _get_recognizer()
    from app.reid.name_anchor import name_anchor
    return {
        "events":   r.events,
        "total":    len(r.events),
        "anchored": name_anchor.get_all(),
    }


@router.post("/session/reset")
def face_reset():
    _get_recognizer().reset_session()
    return {"ok": True}
