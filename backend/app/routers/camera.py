"""
routers/camera.py — Live Camera Endpoints for Retail AI System
"""
import asyncio
import uuid
import cv2
import numpy as np
from datetime import datetime
from fastapi import APIRouter, File, UploadFile, Query
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel

from app.services.oakd_camera import start_camera, stop_camera, get_frame, get_status, start_http_camera
import threading

router = APIRouter(prefix="/camera", tags=["camera"])

# ── All known RTSP cameras ────────────────────────────────────────────────────
RTSP_BASE = "rtsp://frameai:qweRty99@45.121.29.181:30100/Streaming/channels/"

# ── Dataset Collection State (runtime on/off per camera) ────────────────────
_dataset_state: dict = {
    cam["id"]: cam["id"] in {"cam6", "cam7", "cam8"}
    for cam in [
        {"id": "cam1"}, {"id": "cam2"}, {"id": "cam3"}, {"id": "cam4"},
        {"id": "cam5"}, {"id": "cam6"}, {"id": "cam7"}, {"id": "cam8"},
    ]
}


def is_dataset_enabled(camera_id: str) -> bool:
    return _dataset_state.get(camera_id, False)


# ── Retail Intelligence State (in-memory, updated by analytics pipeline) ─────
_retail_state = {
    # Shelf (CAM-3)
    "shelf": {"status": "UNKNOWN", "occupied": 0, "available": 0, "occupancy": 0.0, "last_updated": None},
    # Queue (CAM-4 + CAM-6)
    "queue": {"cam4_count": 0, "cam6_count": 0, "total_queue": 0, "alert": False, "avg_wait_sec": 0, "last_updated": None},
    # Parking (CAM-7)
    "parking": {"vehicles": 0, "capacity": 30, "pct_full": 0.0, "alert": False, "last_updated": None},
    # Security (CAM-5)
    "security": {"alerts": [], "loitering_count": 0, "after_hours_alert": False, "last_updated": None},
    # Conversion (CAM-1 entries vs CAM-4 exits)
    "conversion": {"total_visitors": 0, "total_buyers": 0, "rate_pct": 0.0, "last_updated": None},
    # Heatmap (all indoor cameras combined zone totals)
    "heatmap": {},
    # Per-camera live metrics (updated by analytics pipeline every 15 frames)
    "cam_metrics": {},
}

# Hikvision channel convention:
#   main stream  = x01  (high-res, e.g. 1080p — used for face recognition on cam6)
#   sub stream   = x02  (low-res,  e.g. 480p  — used for AI/YOLO processing)
ALL_CAMERAS = [
    {"id": "cam1", "name": "CAM-1", "sub_channel": 102, "main_channel": 101, "label": "Entrance / Main Gate",  "color": "#0057ff", "mode": "outdoor"},
    {"id": "cam2", "name": "CAM-2", "sub_channel": 202, "main_channel": 201, "label": "Section A / Aisle",     "color": "#16a34a", "mode": "indoor"},
    {"id": "cam3", "name": "CAM-3", "sub_channel": 302, "main_channel": 301, "label": "Section B / Shelves",   "color": "#a855f7", "mode": "indoor"},
    {"id": "cam4", "name": "CAM-4", "sub_channel": 402, "main_channel": 401, "label": "Checkout / Exit",       "color": "#ef4444", "mode": "outdoor"},
    {"id": "cam5", "name": "CAM-5", "sub_channel": 502, "main_channel": 501, "label": "Storage / Back Area",   "color": "#f59e0b", "mode": "vehicle"},
    {"id": "cam6", "name": "CAM-6", "sub_channel": 602, "main_channel": 601, "label": "Cash Counter",          "color": "#06b6d4", "mode": "indoor"},
    {"id": "cam7", "name": "CAM-7", "sub_channel": 702, "main_channel": 701, "label": "Parking / Exterior",    "color": "#ec4899", "mode": "indoor"},
    {"id": "cam8", "name": "CAM-8", "sub_channel": 802, "main_channel": 801, "label": "Loading Dock",          "color": "#84cc16", "mode": "indoor"},
]


@router.get("/list")
def list_cameras():
    """Return all available RTSP cameras with sub + main stream URLs + active job_id."""
    url_to_job = {url: jid for jid, url in _active_rtsp_jobs.items()}
    cameras = []
    for cam in ALL_CAMERAS:
        sub_url  = f"{RTSP_BASE}{cam['sub_channel']}"
        main_url = f"{RTSP_BASE}{cam['main_channel']}"
        cameras.append({
            **cam,
            "sub_stream_url":  sub_url,
            "main_stream_url": main_url,
            "job_id": url_to_job.get(sub_url) or url_to_job.get(main_url),
        })
    return {"cameras": cameras, "total": len(ALL_CAMERAS), "rtsp_base": RTSP_BASE}


# ── Active RTSP jobs — per job_id tracking ───────────────────────────────────
_active_rtsp_jobs: dict[str, str] = {}  # job_id → rtsp_url

# ── Session-level live tracking ───────────────────────────────────────────────
_session = {
    "entries":           0,
    "exits":             0,
    "prev_count":        0,
    "peak_count":        0,
    "unique_people":     0,
    "zone_total_frames": {},
    "zone_current":      {},
    "zone_peak":         {},
    "frame_index":       0,
    # Debounce: only count entry/exit after 3 stable consecutive frames
    "_pending_count":    0,   # candidate new count
    "_pending_streak":   0,   # how many frames in a row this count appeared
    "events":            [],  # [{type, timestamp, person_count}]
}


class CameraStartRequest(BaseModel):
    resolution: str = "720p"
    fps: int = 30


class HttpCameraRequest(BaseModel):
    url: str = "http://localhost:8080/stream"


@router.post("/start")
async def camera_start(req: CameraStartRequest):
    return start_camera(resolution=req.resolution, fps=req.fps)


@router.post("/start-stream")
async def camera_start_stream(req: HttpCameraRequest):
    return start_http_camera(url=req.url)


# ── RTSP → Full Analytics Pipeline ───────────────────────────────────────────
class RtspAnalyticsRequest(BaseModel):
    rtsp_url:         str  = ""   # explicit URL (optional — overrides stream_type)
    stream_type:      str  = "sub"  # "sub" = sub-stream (AI), "main" = main stream (high-res)
    camera_id:        str  = "unknown"
    camera_name:      str  = ""
    zones:      str = "[]"
    entry_zone: str = "[]"
    exit_zone:  str = "[]"
    conf:       float = 0.35
    mode:       str = "indoor"  # "indoor" = full tracking, "outdoor" = count only


@router.post("/rtsp/start")
async def start_rtsp_analytics(req: RtspAnalyticsRequest):
    from app.api.routes import _run_analysis
    from fastapi import HTTPException
    import json

    try:
        zones_data     = json.loads(req.zones)
        entry_zone_pts = json.loads(req.entry_zone)
        exit_zone_pts  = json.loads(req.exit_zone)
    except Exception:
        raise HTTPException(400, "Invalid JSON in zones/entry_zone/exit_zone")

    # ── Resolve camera + stream URLs ─────────────────────────────────────────
    cam_meta = next((c for c in ALL_CAMERAS if c["id"] == req.camera_id), None)

    if req.rtsp_url:
        # Explicit URL provided — use as-is
        ai_url   = req.rtsp_url
        face_url = req.rtsp_url
    elif cam_meta:
        if req.stream_type == "main":
            # User selected main stream — use main for both AI and face
            ai_url   = f"{RTSP_BASE}{cam_meta['main_channel']}"
            face_url = ai_url
        else:
            # Default: sub stream for AI (YOLO), main stream for face recognition (cam6 only)
            ai_url   = f"{RTSP_BASE}{cam_meta['sub_channel']}"
            face_url = f"{RTSP_BASE}{cam_meta['main_channel']}" if req.camera_id == "cam6" else ""
    else:
        raise HTTPException(400, "Provide rtsp_url or a valid camera_id")

    cam_id = cam_meta["id"] if cam_meta else req.camera_id

    job_id = str(uuid.uuid4())
    _active_rtsp_jobs[job_id] = ai_url

    try:
        from app.database.db import SessionLocal
        from app.database.models import AnalyticsJob, JobStatus
        with SessionLocal() as db:
            db.add(AnalyticsJob(
                job_id=job_id,
                filename=f"RTSP: {ai_url}",
                status=JobStatus.PROCESSING,
                progress=0,
            ))
            db.commit()
    except Exception:
        pass

    threading.Thread(
        target=_run_analysis,
        args=(ai_url, job_id, zones_data, entry_zone_pts, exit_zone_pts, req.conf),
        kwargs={
            "mode":             req.mode,
            "dataset_rtsp_url": face_url,
            "camera_id":        cam_id,
            "camera_name":      req.camera_name or cam_id,
        },
        daemon=True,
    ).start()

    return {
        "status":      "processing",
        "job_id":      job_id,
        "ai_url":      ai_url,
        "face_url":    face_url or None,
        "stream_type": req.stream_type,
        "mode":        req.mode,
    }


@router.get("/rtsp/status")
async def rtsp_status():
    return {"active_jobs": list(_active_rtsp_jobs.keys()), "count": len(_active_rtsp_jobs)}


# ── Cross-Camera Person Movement APIs ────────────────────────────────────────
@router.get("/tracking/person/{global_id}")
async def get_person_journey(global_id: int):
    """Get full camera journey for a specific global person ID."""
    from app.database.db import SessionLocal
    from app.database.models import PersonMovementLog
    with SessionLocal() as db:
        logs = (
            db.query(PersonMovementLog)
            .filter(PersonMovementLog.global_id == global_id)
            .order_by(PersonMovementLog.wall_time)
            .all()
        )
    return {
        "global_id": global_id,
        "total_events": len(logs),
        "journey": [
            {
                "camera_id":   l.camera_id,
                "camera_name": l.camera_name,
                "event_type":  l.event_type,
                "zone":        l.zone,
                "wall_time":   str(l.wall_time),
            }
            for l in logs
        ],
    }


@router.get("/tracking/active")
async def get_active_persons():
    """Get all persons currently visible across all cameras with their global IDs."""
    from app.reid.global_registry import global_registry
    active = global_registry.get_active_on_camera
    result = {}
    for cam in ALL_CAMERAS:
        cam_active = global_registry.get_active_on_camera(cam["id"])
        if cam_active:
            result[cam["id"]] = {
                "camera_name": cam["label"],
                "persons": list(cam_active.values()),
            }
    return {
        "total_unique_ever": global_registry.total_unique,
        "cameras": result,
    }


@router.get("/tracking/recent")
async def get_recent_movements(limit: int = 50):
    """Get recent cross-camera movement events (latest first)."""
    from app.database.db import SessionLocal
    from app.database.models import PersonMovementLog
    with SessionLocal() as db:
        logs = (
            db.query(PersonMovementLog)
            .order_by(PersonMovementLog.wall_time.desc())
            .limit(limit)
            .all()
        )
    return {
        "total": len(logs),
        "events": [
            {
                "id":          l.id,
                "global_id":   l.global_id,
                "camera_id":   l.camera_id,
                "camera_name": l.camera_name,
                "event_type":  l.event_type,
                "zone":        l.zone,
                "wall_time":   str(l.wall_time),
            }
            for l in logs
        ],
    }


# ── Retail Intelligence APIs ─────────────────────────────────────────────────

@router.get("/retail/shelf-status")
def retail_shelf_status():
    """CAM-3 (Section B/Shelves) — real-time shelf occupancy status."""
    s = _retail_state["shelf"]
    return {
        "camera": "CAM-3",
        "location": "Section B / Shelves",
        **s,
        "alert": s["status"] in ("EMPTY", "LOW STOCK"),
        "action_required": s["status"] == "EMPTY",
        "recommendation": (
            "🚨 Restock immediately — shelf is empty!" if s["status"] == "EMPTY"
            else "⚠️ Shelf running low — plan restock soon." if s["status"] == "LOW STOCK"
            else "✅ Shelf stock is normal."
        ),
    }


@router.get("/retail/queue-status")
def retail_queue_status():
    """CAM-4 (Checkout) + CAM-6 (Cash Counter) — queue length & wait time."""
    q = _retail_state["queue"]
    return {
        "cameras": ["CAM-4", "CAM-6"],
        "locations": ["Checkout / Exit", "Cash Counter"],
        **q,
        "recommendation": (
            "🚨 Queue critical — open additional counter!" if q["total_queue"] >= 8
            else "⚠️ Queue building up — monitor closely." if q["total_queue"] >= 4
            else "✅ Queue is manageable."
        ),
    }


@router.get("/retail/parking")
def retail_parking():
    """CAM-7 (Parking/Exterior) — vehicle count & parking availability."""
    p = _retail_state["parking"]
    available = max(0, p["capacity"] - p["vehicles"])
    return {
        "camera": "CAM-7",
        "location": "Parking / Exterior",
        **p,
        "available_spots": available,
        "status": "FULL" if available == 0 else "ALMOST_FULL" if p["pct_full"] >= 80 else "AVAILABLE",
        "recommendation": (
            "🚨 Parking full — redirect incoming vehicles!" if available == 0
            else "⚠️ Parking almost full." if p["pct_full"] >= 80
            else "✅ Parking available."
        ),
    }


@router.get("/retail/security-alerts")
def retail_security_alerts():
    """CAM-5 (Storage/Back Area) — after-hours movement & loitering detection."""
    from datetime import datetime
    sec = _retail_state["security"]
    now = datetime.now()
    # Store hours: 9 AM – 10 PM
    is_after_hours = now.hour < 9 or now.hour >= 22
    return {
        "camera": "CAM-5",
        "location": "Storage / Back Area",
        "is_after_hours": is_after_hours,
        "store_hours": "09:00 – 22:00",
        **sec,
        "active_alert": sec["after_hours_alert"] or sec["loitering_count"] > 0,
    }


@router.get("/retail/conversion")
def retail_conversion():
    """CAM-1 (Entrance) vs CAM-4 (Exit/Checkout) — visitor to buyer conversion rate."""
    c = _retail_state["conversion"]
    # Pull live data from cam_metrics
    cam1 = _retail_state["cam_metrics"].get("cam1", {})
    cam4 = _retail_state["cam_metrics"].get("cam4", {})
    visitors = cam1.get("entries", 0) or c["total_visitors"]
    buyers   = cam4.get("exits",   0) or c["total_buyers"]
    rate     = round((buyers / visitors * 100), 1) if visitors > 0 else 0.0
    return {
        "cameras": ["CAM-1", "CAM-4"],
        "total_visitors": visitors,
        "total_buyers": buyers,
        "conversion_rate_pct": rate,
        "non_buyers": max(0, visitors - buyers),
        "insight": (
            f"🎯 {rate}% conversion — excellent!" if rate >= 40
            else f"📊 {rate}% conversion — room for improvement." if rate >= 20
            else f"⚠️ {rate}% conversion — investigate drop-off zones."
        ),
        "last_updated": c["last_updated"],
    }


@router.get("/retail/heatmap")
def retail_heatmap():
    """All indoor cameras combined — zone-level customer heatmap."""
    combined = {}
    indoor_cams = ["cam2", "cam3", "cam6", "cam7", "cam8"]
    for cam_id in indoor_cams:
        metrics = _retail_state["cam_metrics"].get(cam_id, {})
        zone_totals = metrics.get("zone_totals", {})
        for zone, count in zone_totals.items():
            combined[zone] = combined.get(zone, 0) + count
    # Also merge stored heatmap
    for zone, count in _retail_state["heatmap"].items():
        combined[zone] = combined.get(zone, 0) + count
    total = sum(combined.values()) or 1
    ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)
    return {
        "zones": combined,
        "ranked": [{"zone": z, "count": c, "pct": round(c / total * 100, 1)} for z, c in ranked],
        "hottest_zone": ranked[0][0] if ranked else None,
        "coldest_zone": ranked[-1][0] if ranked else None,
        "total_detections": total,
    }


@router.get("/retail/dashboard")
def retail_dashboard():
    """Single endpoint — all retail intelligence combined for dashboard."""
    from datetime import datetime
    now = datetime.now()
    is_after_hours = now.hour < 9 or now.hour >= 22

    cam1 = _retail_state["cam_metrics"].get("cam1", {})
    cam4 = _retail_state["cam_metrics"].get("cam4", {})
    visitors = cam1.get("entries", 0)
    buyers   = cam4.get("exits",   0)
    rate     = round((buyers / visitors * 100), 1) if visitors > 0 else 0.0

    q = _retail_state["queue"]
    p = _retail_state["parking"]
    s = _retail_state["shelf"]
    sec = _retail_state["security"]

    # Total inside across all cameras
    total_inside = sum(
        m.get("currently_inside", 0)
        for m in _retail_state["cam_metrics"].values()
    )

    alerts = []
    if s["status"] == "EMPTY":       alerts.append({"type": "shelf",    "severity": "critical", "msg": "Shelf empty — restock now!"})
    if s["status"] == "LOW STOCK":   alerts.append({"type": "shelf",    "severity": "warning",  "msg": "Shelf low stock"})
    if q["total_queue"] >= 8:        alerts.append({"type": "queue",    "severity": "critical", "msg": f"Queue critical: {q['total_queue']} people"})
    if q["total_queue"] >= 4:        alerts.append({"type": "queue",    "severity": "warning",  "msg": f"Queue building: {q['total_queue']} people"})
    if p["pct_full"] >= 100:         alerts.append({"type": "parking",  "severity": "critical", "msg": "Parking full!"})
    if sec["after_hours_alert"]:     alerts.append({"type": "security", "severity": "critical", "msg": "After-hours movement detected!"})
    if sec["loitering_count"] > 0:   alerts.append({"type": "security", "severity": "warning",  "msg": f"Loitering detected: {sec['loitering_count']} person(s)"})

    return {
        "timestamp": now.isoformat(),
        "store_open": not is_after_hours,
        "total_inside": total_inside,
        "conversion_rate_pct": rate,
        "total_visitors": visitors,
        "total_buyers": buyers,
        "shelf": s,
        "queue": q,
        "parking": {**p, "available": max(0, p["capacity"] - p["vehicles"])},
        "security": sec,
        "active_alerts": alerts,
        "alert_count": len(alerts),
    }


def update_retail_state(camera_id: str, metrics: dict) -> None:
    """
    Called by analytics pipeline every 15 frames to update retail intelligence state.
    camera_id: 'cam1' .. 'cam8'
    metrics: live analytics dict from process_video progress_cb
    """
    from datetime import datetime
    now = datetime.utcnow().isoformat()

    # Store per-camera metrics
    _retail_state["cam_metrics"][camera_id] = {**metrics, "last_updated": now}

    currently_inside = metrics.get("currently_inside", 0)
    zone_current     = metrics.get("zone_current", {})
    zone_totals      = metrics.get("zone_totals", {})

    # CAM-3: Shelf monitoring
    if camera_id == "cam3":
        shelf_status = metrics.get("shelf_status", "UNKNOWN")
        _retail_state["shelf"].update({
            "status":        shelf_status,
            "occupancy":     metrics.get("shelf_occupancy", 0.0),
            "occupied":      metrics.get("shelf_occupied", 0),
            "available":     metrics.get("shelf_available", 0),
            "empty_zones":   metrics.get("shelf_empty_zones", 0),
            "reduced_zones": metrics.get("shelf_reduced_zones", 0),
            "last_updated":  now,
        })

    # CAM-4 + CAM-6: Queue monitoring
    if camera_id == "cam4":
        _retail_state["queue"]["cam4_count"] = currently_inside
        _retail_state["queue"]["last_updated"] = now
    if camera_id == "cam6":
        _retail_state["queue"]["cam6_count"] = currently_inside
        _retail_state["queue"]["last_updated"] = now
    if camera_id in ("cam4", "cam6"):
        total_q = _retail_state["queue"]["cam4_count"] + _retail_state["queue"]["cam6_count"]
        _retail_state["queue"]["total_queue"] = total_q
        _retail_state["queue"]["alert"] = total_q >= 4
        _retail_state["queue"]["avg_wait_sec"] = metrics.get("dwell_avg_sec", 0)

    # CAM-7: Parking
    if camera_id == "cam7":
        vehicles = currently_inside
        capacity = _retail_state["parking"]["capacity"]
        _retail_state["parking"].update({
            "vehicles": vehicles,
            "pct_full": round(vehicles / capacity * 100, 1),
            "alert": vehicles >= capacity * 0.9,
            "last_updated": now,
        })

    # CAM-5: Security / loitering
    if camera_id == "cam5":
        from datetime import datetime as dt
        hour = dt.now().hour
        after_hours = hour < 9 or hour >= 22
        dwell_max = metrics.get("dwell_max_sec", 0)
        loitering = currently_inside if dwell_max > 300 else 0  # 5+ min = loitering
        new_alerts = list(_retail_state["security"]["alerts"][-9:])  # keep last 10
        if after_hours and currently_inside > 0:
            new_alerts.append({"time": now, "type": "after_hours", "count": currently_inside})
        if loitering > 0:
            new_alerts.append({"time": now, "type": "loitering", "count": loitering})
        _retail_state["security"].update({
            "loitering_count": loitering,
            "after_hours_alert": after_hours and currently_inside > 0,
            "alerts": new_alerts,
            "last_updated": now,
        })

    # CAM-1: Conversion tracking (visitor count)
    if camera_id == "cam1":
        _retail_state["conversion"]["total_visitors"] = metrics.get("entries", 0)
        _retail_state["conversion"]["last_updated"] = now

    # CAM-4: Conversion tracking (buyer count)
    if camera_id == "cam4":
        _retail_state["conversion"]["total_buyers"] = metrics.get("exits", 0)
        v = _retail_state["conversion"]["total_visitors"]
        b = _retail_state["conversion"]["total_buyers"]
        _retail_state["conversion"]["rate_pct"] = round(b / v * 100, 1) if v > 0 else 0.0

    # Heatmap: accumulate zone totals from all indoor cameras
    indoor_cams = {"cam2", "cam3", "cam6", "cam7", "cam8"}
    if camera_id in indoor_cams:
        for zone, count in zone_totals.items():
            _retail_state["heatmap"][zone] = _retail_state["heatmap"].get(zone, 0) + count


@router.get("/dataset/status")
async def dataset_status():
    """Per-camera dataset collection on/off state + day-wise image/label counts."""
    from app.config import DATASET_DIR, DATASET_COLLECT
    import os
    result = {}
    for cam in ALL_CAMERAS:
        cid = cam["id"]
        cam_dir = os.path.join(DATASET_DIR, cid)
        total_imgs = 0
        total_lbls = 0
        days = {}
        if os.path.exists(cam_dir):
            for day in sorted(os.listdir(cam_dir)):
                day_path = os.path.join(cam_dir, day)
                if not os.path.isdir(day_path) or day.startswith('.'):
                    continue
                imgs = len([f for f in os.listdir(os.path.join(day_path, "images")) if not f.startswith('.')]) if os.path.exists(os.path.join(day_path, "images")) else 0
                lbls = len([f for f in os.listdir(os.path.join(day_path, "labels")) if not f.startswith('.')]) if os.path.exists(os.path.join(day_path, "labels")) else 0
                days[day] = {"images": imgs, "labels": lbls}
                total_imgs += imgs
                total_lbls += lbls
        result[cid] = {
            "enabled":   _dataset_state.get(cid, False),
            "images":    total_imgs,
            "labels":    total_lbls,
            "days":      days,
            "cam_name":  cam["name"],
            "cam_label": cam["label"],
        }
    total_imgs = sum(v["images"] for v in result.values())
    total_lbls = sum(v["labels"] for v in result.values())
    return {
        "global_collect": DATASET_COLLECT,
        "cameras": result,
        "total_images": total_imgs,
        "total_labels": total_lbls,
    }


@router.post("/dataset/toggle/{cam_id}")
async def dataset_toggle(cam_id: str):
    """Toggle dataset collection on/off for a specific camera."""
    from app.config import DATASET_DIR
    import os
    if cam_id not in _dataset_state:
        from fastapi import HTTPException
        raise HTTPException(404, f"Unknown camera: {cam_id}")
    _dataset_state[cam_id] = not _dataset_state[cam_id]
    # Ensure dirs exist when enabling
    if _dataset_state[cam_id]:
        os.makedirs(os.path.join(DATASET_DIR, cam_id, "images"), exist_ok=True)
        os.makedirs(os.path.join(DATASET_DIR, cam_id, "labels"), exist_ok=True)
    return {"camera_id": cam_id, "enabled": _dataset_state[cam_id]}


@router.post("/dataset/toggle-all")
async def dataset_toggle_all(enable: bool):
    """Enable or disable dataset collection for ALL cameras at once."""
    from app.config import DATASET_DIR
    import os
    for cid in _dataset_state:
        _dataset_state[cid] = enable
        if enable:
            os.makedirs(os.path.join(DATASET_DIR, cid, "images"), exist_ok=True)
            os.makedirs(os.path.join(DATASET_DIR, cid, "labels"), exist_ok=True)
    return {"enabled": enable, "cameras": dict(_dataset_state)}


@router.get("/dataset/stats")
async def dataset_stats():
    """How many frames collected per camera for fine-tuning dataset."""
    from app.config import DATASET_DIR, DATASET_CAMERAS
    import os
    per_cam = {}
    total_images = 0
    total_labels = 0
    for cam in DATASET_CAMERAS:
        img_dir = os.path.join(DATASET_DIR, cam, "images")
        lbl_dir = os.path.join(DATASET_DIR, cam, "labels")
        imgs = len(os.listdir(img_dir)) if os.path.exists(img_dir) else 0
        lbls = len(os.listdir(lbl_dir)) if os.path.exists(lbl_dir) else 0
        per_cam[cam] = {"images": imgs, "labels": lbls}
        total_images += imgs
        total_labels += lbls
    return {"total_images": total_images, "total_labels": total_labels, "per_camera": per_cam, "dataset_dir": DATASET_DIR}


@router.post("/rtsp/stop/{job_id}")
async def stop_rtsp_job(job_id: str):
    """Stop a specific RTSP analytics job by job_id."""
    from app.database.db import SessionLocal
    from app.database.models import AnalyticsJob, JobStatus
    import datetime

    _active_rtsp_jobs.pop(job_id, None)

    db = SessionLocal()
    try:
        job = db.query(AnalyticsJob).filter(AnalyticsJob.job_id == job_id).first()
        if job and job.status == JobStatus.PROCESSING:
            job.status       = JobStatus.COMPLETED
            job.completed_at = datetime.datetime.utcnow()
            job.progress     = 100
            db.commit()
    finally:
        db.close()

    return {"status": "stopped", "job_id": job_id}


@router.post("/zones/reload")
async def reload_zones():
    """Hot-reload polygon zones for all running camera pipelines.
    Call this after saving/updating zones in the frontend zone editor.
    """
    from app.services.analytics_service import _active_pipelines
    reloaded = []
    for cam_id, pipeline in _active_pipelines.items():
        try:
            pipeline.reload_zones()
            reloaded.append({"camera_id": cam_id, "zones": len(pipeline._zones)})
        except Exception as e:
            reloaded.append({"camera_id": cam_id, "error": str(e)})
    return {"reloaded": reloaded, "total": len(reloaded)}


@router.post("/rtsp/stop-all")
async def stop_all_rtsp_jobs():
    """Stop all active RTSP analytics jobs."""
    from app.database.db import SessionLocal
    from app.database.models import AnalyticsJob, JobStatus
    import datetime

    stopped = list(_active_rtsp_jobs.keys())
    _active_rtsp_jobs.clear()

    db = SessionLocal()
    try:
        for jid in stopped:
            job = db.query(AnalyticsJob).filter(AnalyticsJob.job_id == jid).first()
            if job and job.status == JobStatus.PROCESSING:
                job.status       = JobStatus.COMPLETED
                job.completed_at = datetime.datetime.utcnow()
                job.progress     = 100
        db.commit()
    finally:
        db.close()

    return {"status": "stopped", "stopped_jobs": stopped}


@router.get("/rtsp/preview-frame")
async def rtsp_preview_frame(rtsp_url: str = "", camera_id: str = "", stream_type: str = "sub"):
    """Grab a single frame from RTSP stream as JPEG (for zone drawing).
    Pass either rtsp_url directly, or camera_id + stream_type (sub/main).
    """
    import cv2, os
    from fastapi import HTTPException
    from fastapi.responses import Response

    if not rtsp_url:
        cam_meta = next((c for c in ALL_CAMERAS if c["id"] == camera_id), None)
        if not cam_meta:
            raise HTTPException(400, "Provide rtsp_url or valid camera_id")
        channel  = cam_meta["main_channel"] if stream_type == "main" else cam_meta["sub_channel"]
        rtsp_url = f"{RTSP_BASE}{channel}"
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|buffer_size;2000000"
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise HTTPException(503, f"Cannot connect to RTSP stream: {rtsp_url}")

    # Skip more frames for H.265 — needs keyframe to decode cleanly
    for _ in range(20):
        cap.read()
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise HTTPException(503, "Could not read frame from RTSP stream")

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return Response(content=buf.tobytes(), media_type="image/jpeg")


@router.post("/stop")
async def camera_stop():
    return stop_camera()


@router.get("/status")
async def camera_status():
    return {**get_status(), "source": "oak-d"}


@router.get("/frame")
async def camera_frame():
    frame = get_frame()
    if frame is None:
        return Response(content=b"", status_code=503, headers={"X-Error": "Camera not ready"})
    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return Response(content=jpeg.tobytes(), media_type="image/jpeg")


@router.get("/stream")
async def camera_stream():
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


async def _mjpeg_generator():
    while True:
        frame = get_frame()
        if frame is not None:
            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
        await asyncio.sleep(0.033)


class InspectLiveRequest(BaseModel):
    zones: list = []   # [{"name": "Entrance", "points": [[x,y],...]}]


@router.post("/inspect-live")
async def inspect_live(req: InspectLiveRequest = None):
    """Capture OAK-D frame → YOLO → cumulative session analytics."""
    frame = get_frame()
    if frame is None:
        return {"error": "no_frame", "message": "Camera not connected"}
    zone_names = [z["name"] for z in (req.zones if req and req.zones else [])]
    raw = _run_yolo_on_frame(frame, zone_names=zone_names)
    return _update_session(raw)


class SimFrameRequest(BaseModel):
    person_count: int = 0
    zone_counts: dict = {}
    entries: int = 0
    exits: int = 0


@router.post("/session/push")
async def session_push(req: SimFrameRequest):
    """Push a simulated frame — simulation already handles entry/exit counting client-side."""
    s = _session
    s["frame_index"] += 1
    curr = req.person_count
    s["peak_count"]    = max(s["peak_count"], curr)
    s["unique_people"] = s["peak_count"]
    s["prev_count"]    = curr
    s["entries"]       = req.entries
    s["exits"]         = req.exits
    s["zone_current"]  = dict(req.zone_counts)
    for z, cnt in req.zone_counts.items():
        s["zone_total_frames"][z] = s["zone_total_frames"].get(z, 0) + cnt
        s["zone_peak"][z]         = max(s["zone_peak"].get(z, 0), cnt)
    # entries/exits come from frontend simulation — push them directly
    return {"ok": True}


@router.post("/session/push-webcam")
async def session_push_webcam(req: SimFrameRequest):
    """Push webcam person_count — uses debounce logic for entry/exit counting."""
    raw = {"person_count": req.person_count, "zone_counts": req.zone_counts}
    snap = _update_session(raw)
    return snap


@router.post("/session/reset")
async def session_reset():
    """Reset live session counters."""
    _session.update({
        "entries": 0, "exits": 0, "prev_count": 0, "peak_count": 0,
        "unique_people": 0, "zone_total_frames": {}, "zone_current": {},
        "zone_peak": {}, "frame_index": 0,
        "_pending_count": 0, "_pending_streak": 0, "events": [],
    })
    return {"ok": True, "message": "Session reset"}


@router.get("/session/events")
async def session_events():
    """Return live session entry/exit events for Footfall Log."""
    return {"events": list(_session["events"])}


def get_session_snapshot() -> dict:
    """Return a JSON-safe copy of current session — used by dashboard."""
    s = _session
    fi = max(s["frame_index"], 1)
    avg_per_frame = {
        z: round(s["zone_total_frames"][z] / fi, 2)
        for z in s["zone_total_frames"]
    }
    most_popular = (
        max(s["zone_current"], key=s["zone_current"].get)
        if s["zone_current"] else None
    )
    return {
        "entries":           s["entries"],
        "exits":             s["exits"],
        "currently_inside":  s["prev_count"],
        "peak_count":        s["peak_count"],
        "unique_people":     s["unique_people"],
        "zone_current":      dict(s["zone_current"]),
        "zone_peak":         dict(s["zone_peak"]),
        "zone_total_frames": dict(s["zone_total_frames"]),
        "avg_per_frame":     avg_per_frame,
        "most_popular":      most_popular,
        "frame_index":       s["frame_index"],
    }


def _update_session(raw: dict) -> dict:
    """Update in-memory session with debounced entry/exit counting."""
    s = _session
    s["frame_index"] += 1
    curr = raw.get("person_count", 0)
    prev = s["prev_count"]

    # Debounce: only commit count change after 3 consecutive stable frames
    DEBOUNCE = 3
    if curr == s["_pending_count"]:
        s["_pending_streak"] += 1
    else:
        s["_pending_count"]  = curr
        s["_pending_streak"] = 1

    if s["_pending_streak"] >= DEBOUNCE and curr != prev:
        ts = datetime.utcnow().isoformat()
        if curr > prev:
            for _ in range(curr - prev):
                s["events"].append({"event_type": "entry", "timestamp": ts, "person_count": curr})
            s["entries"] += (curr - prev)
        else:
            for _ in range(prev - curr):
                s["events"].append({"event_type": "exit", "timestamp": ts, "person_count": curr})
            s["exits"]   += (prev - curr)
        s["prev_count"] = curr

    s["peak_count"]    = max(s["peak_count"], curr)
    s["unique_people"] = s["peak_count"]

    # Zone tracking
    zone_counts = raw.get("zone_counts", {})
    s["zone_current"] = zone_counts
    for z, cnt in zone_counts.items():
        s["zone_total_frames"][z] = s["zone_total_frames"].get(z, 0) + cnt
        s["zone_peak"][z]         = max(s["zone_peak"].get(z, 0), cnt)

    snap = get_session_snapshot()

    return {
        **raw,
        "entries":             snap["entries"],
        "exits":               snap["exits"],
        "currently_inside":    curr,
        "total_unique_people": snap["unique_people"],
        "peak_count":          snap["peak_count"],
        "shelf_status":        "NO SHELF DETECTED",
        "zones": {
            "most_popular":      snap["most_popular"],
            "current_occupancy": snap["zone_current"],
            "unique_visitors":   snap["zone_peak"],
            "avg_per_frame":     snap["avg_per_frame"],
        },
    }


@router.post("/inspect-image")
async def inspect_image(file: UploadFile = File(...), conf: float = Query(0.40)):
    """Upload image → YOLO person detection."""
    raw = await file.read()
    if not raw:
        return {"error": "empty_file"}
    nparr = np.frombuffer(raw, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        return {"error": "invalid_image"}
    return _run_yolo_on_frame(frame, conf=conf)


def _run_yolo_on_frame(frame: np.ndarray, conf: float = 0.40, zone_names: list = None) -> dict:
    """Run YOLOv8n person detection on a frame."""
    import time, os
    t0 = time.perf_counter()
    frame_id = f"FRAME-{uuid.uuid4().hex[:6].upper()}"
    h, w = frame.shape[:2]

    try:
        from ultralytics import YOLO
        model_path = os.path.join(os.path.dirname(__file__), "..", "..", "yolov8n.pt")
        if not hasattr(_run_yolo_on_frame, "_model"):
            _run_yolo_on_frame._model = YOLO(model_path if os.path.exists(model_path) else "yolov8n.pt")

        rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = _run_yolo_on_frame._model(rgb, conf=conf, classes=[0], verbose=False, device="cpu")

        persons = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                # Use user-drawn zone names if provided, else fallback to grid
                if zone_names:
                    cx_pct = (x1 + x2) / 2 / w
                    idx = min(int(cx_pct * len(zone_names)), len(zone_names) - 1)
                    zone = zone_names[idx]
                else:
                    zone = _get_zone(x1, y1, x2, y2, w, h)
                persons.append({
                    "bbox_pct":   [round(x1/w*100,1), round(y1/h*100,1), round(x2/w*100,1), round(y2/h*100,1)],
                    "confidence": round(float(box.conf[0]), 3),
                    "zone":       zone,
                })

        person_count = len(persons)
        zone_counts  = {}
        for p in persons:
            zone_counts[p["zone"]] = zone_counts.get(p["zone"], 0) + 1

        density = "LOW"
        if person_count >= 20:   density = "CRITICAL"
        elif person_count >= 12: density = "HIGH"
        elif person_count >= 6:  density = "MEDIUM"

        return {
            "frame_id":     frame_id,
            "person_count": person_count,
            "density":      density,
            "persons":      persons,
            "zone_counts":  zone_counts,
            "infer_ms":     round((time.perf_counter() - t0) * 1000),
            "frame_size":   f"{w}x{h}",
            "timestamp":    datetime.utcnow().isoformat(),
            "model":        "yolov8n",
        }

    except Exception as e:
        return {
            "frame_id":     frame_id,
            "person_count": 0,
            "density":      "UNKNOWN",
            "persons":      [],
            "zone_counts":  {},
            "infer_ms":     round((time.perf_counter() - t0) * 1000),
            "error":        str(e),
            "timestamp":    datetime.utcnow().isoformat(),
        }


def _get_zone(x1, y1, x2, y2, w, h) -> str:
    cx = (x1 + x2) / 2 / w
    cy = (y1 + y2) / 2 / h
    row = "Entrance" if cy < 0.33 else "Mid" if cy < 0.66 else "Checkout"
    col = "Left"     if cx < 0.33 else "Center" if cx < 0.66 else "Right"
    return {
        ("Entrance","Left"):"Entrance", ("Entrance","Center"):"Entrance", ("Entrance","Right"):"Electronics",
        ("Mid","Left"):"Apparel",       ("Mid","Center"):"Grocery",       ("Mid","Right"):"Electronics",
        ("Checkout","Left"):"Checkout", ("Checkout","Center"):"Checkout", ("Checkout","Right"):"Checkout",
    }.get((row, col), "Grocery")
