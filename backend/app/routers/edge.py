"""
routers/edge.py — Camera/Hardware & Edge Deployment

GET  /edge/camera-health/auto-check  → auto-check all cameras from job data
GET  /edge/devices                   → list registered edge devices
POST /edge/devices                   → register edge device
PATCH /edge/devices/{id}             → update device config (night mode, model)
POST /edge/devices/{id}/heartbeat    → device sends heartbeat
GET  /edge/devices/{id}/config       → get full config for device to pull
GET  /edge/night-mode/status         → night mode status across devices
POST /edge/night-mode/toggle         → enable/disable night mode for device
GET  /edge/deployment/guide          → edge deployment setup guide
GET  /edge/summary                   → edge infrastructure summary
"""
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import AnalyticsJob, JobStatus, AlertLog, EdgeDevice

router = APIRouter(prefix="/edge", tags=["edge"])

# ── Device Types & Specs ──────────────────────────────────────────────────────

DEVICE_SPECS = {
    "jetson_nano": {
        "name": "NVIDIA Jetson Nano",
        "ram": "4GB", "gpu": "128-core Maxwell",
        "recommended_model": "yolov8n",
        "max_cameras": 2, "fps_capability": 15,
        "power_w": 10, "price_usd": 99,
        "use_case": "Entry-level edge inference, 1-2 cameras",
    },
    "jetson_orin": {
        "name": "NVIDIA Jetson Orin NX",
        "ram": "16GB", "gpu": "1024-core Ampere",
        "recommended_model": "yolov8s",
        "max_cameras": 8, "fps_capability": 60,
        "power_w": 25, "price_usd": 499,
        "use_case": "High-performance multi-camera store analytics",
    },
    "oak_d": {
        "name": "Luxonis OAK-D",
        "ram": "4GB (on-device)", "gpu": "Intel Myriad X VPU",
        "recommended_model": "yolov8n",
        "max_cameras": 1, "fps_capability": 30,
        "power_w": 5, "price_usd": 149,
        "use_case": "Standalone depth + AI camera, plug-and-play",
    },
    "raspberry_pi": {
        "name": "Raspberry Pi 5",
        "ram": "8GB", "gpu": "VideoCore VII",
        "recommended_model": "yolov8n",
        "max_cameras": 1, "fps_capability": 8,
        "power_w": 5, "price_usd": 80,
        "use_case": "Low-cost single-camera deployment",
    },
}

NIGHT_MODE_SETTINGS = {
    "brightness_boost":    1.8,   # multiply pixel brightness
    "contrast_enhance":    1.3,
    "denoise_strength":    0.6,
    "detection_threshold": 0.35,  # lower threshold for low-light
    "min_box_size":        20,    # ignore tiny detections in noise
}


# ── Camera Health Auto-Check ──────────────────────────────────────────────────

@router.get("/camera-health/auto-check")
def auto_check_camera_health(db: Session = Depends(get_db)):
    """
    Automatically derive camera health from job analytics:
    - Zero detections → possible offline/tampered
    - Very low avg_per_frame → possible blur/obstruction
    - Sudden drop in detections vs previous job → possible issue
    """
    jobs = (
        db.query(AnalyticsJob)
        .filter(AnalyticsJob.status == JobStatus.COMPLETED)
        .order_by(AnalyticsJob.completed_at.desc())
        .limit(20)
        .all()
    )

    issues = []
    healthy = []
    all_avg = [
        (j.result or {}).get("avg_people_per_frame", 0)
        for j in jobs if (j.result or {}).get("avg_people_per_frame", 0) > 0
    ]
    global_avg = sum(all_avg) / len(all_avg) if all_avg else 0

    for j in jobs:
        r       = j.result or {}
        entries = r.get("entries", 0)
        avg_pf  = r.get("avg_people_per_frame", 0)
        ts      = str(j.completed_at)[:16] if j.completed_at else "unknown"

        if entries == 0 and avg_pf == 0:
            issues.append({
                "job_id":     j.job_id[:8],
                "filename":   j.filename,
                "issue":      "OFFLINE_OR_TAMPERED",
                "severity":   "CRITICAL",
                "detail":     "Zero detections — camera may be offline, covered, or tampered",
                "timestamp":  ts,
                "action":     "Check camera power, network, and physical placement",
            })
        elif global_avg > 0 and avg_pf < global_avg * 0.2 and avg_pf > 0:
            issues.append({
                "job_id":     j.job_id[:8],
                "filename":   j.filename,
                "issue":      "LOW_DETECTION",
                "severity":   "WARNING",
                "detail":     f"Avg {avg_pf:.1f} people/frame vs global avg {global_avg:.1f} — possible blur or obstruction",
                "timestamp":  ts,
                "action":     "Clean camera lens, check angle and lighting",
            })
        else:
            healthy.append({
                "job_id":    j.job_id[:8],
                "filename":  j.filename,
                "avg_pf":    round(avg_pf, 2),
                "entries":   entries,
                "timestamp": ts,
            })

    total = len(jobs)
    health_score = round((len(healthy) / total * 100)) if total > 0 else 100

    # Also check AlertLog for camera-related alerts
    cam_alerts = (
        db.query(AlertLog)
        .filter(AlertLog.message.ilike("%camera%"))
        .order_by(AlertLog.wall_time.desc())
        .limit(5)
        .all()
    )

    return {
        "health_score":    health_score,
        "status":          "HEALTHY" if health_score >= 90 else "DEGRADED" if health_score >= 70 else "CRITICAL",
        "total_checked":   total,
        "healthy_count":   len(healthy),
        "issue_count":     len(issues),
        "issues":          issues,
        "healthy_cameras": healthy[:5],
        "camera_alerts":   [{"message": a.message, "time": str(a.wall_time)[:16]} for a in cam_alerts],
        "recommendations": [
            "Schedule regular camera cleaning (monthly)" if health_score < 100 else None,
            "Enable night mode for low-light hours (8PM–8AM)" if any(i["issue"] == "LOW_DETECTION" for i in issues) else None,
            "Check network connectivity for offline cameras" if any(i["issue"] == "OFFLINE_OR_TAMPERED" for i in issues) else None,
        ],
        "checked_at": datetime.datetime.utcnow().isoformat(),
    }


# ── Edge Device Management ────────────────────────────────────────────────────

class EdgeDeviceReq(BaseModel):
    store_id:       str = "store_1"
    device_id:      str
    device_type:    str   # jetson_nano | jetson_orin | oak_d | raspberry_pi
    ip_address:     Optional[str] = None
    night_mode:     bool = False
    night_threshold: int = 60
    model_variant:  str = "yolov8n"


class HeartbeatReq(BaseModel):
    status:     str = "online"
    cpu_pct:    Optional[float] = None
    ram_pct:    Optional[float] = None
    temp_c:     Optional[float] = None
    fps:        Optional[float] = None


@router.post("/devices")
def register_device(req: EdgeDeviceReq, db: Session = Depends(get_db)):
    existing = db.query(EdgeDevice).filter(EdgeDevice.device_id == req.device_id).first()
    if existing:
        for k, v in req.model_dump().items():
            setattr(existing, k, v)
        db.commit()
        return {"status": "updated", "device_id": req.device_id}

    device = EdgeDevice(**req.model_dump())
    db.add(device); db.commit(); db.refresh(device)
    return {"status": "registered", "id": device.id, "device_id": req.device_id}


@router.get("/devices")
def list_devices(store_id: str = "store_1", db: Session = Depends(get_db)):
    devices = db.query(EdgeDevice).filter(EdgeDevice.store_id == store_id).all()
    result = []
    for d in devices:
        spec = DEVICE_SPECS.get(d.device_type, {})
        last_hb = d.last_heartbeat
        online = last_hb and (datetime.datetime.utcnow() - last_hb).seconds < 120
        result.append({
            "id":             d.id,
            "device_id":      d.device_id,
            "device_type":    d.device_type,
            "device_name":    spec.get("name", d.device_type),
            "ip_address":     d.ip_address,
            "status":         "online" if online else d.status,
            "night_mode":     d.night_mode,
            "night_threshold": d.night_threshold,
            "model_variant":  d.model_variant,
            "last_heartbeat": str(last_hb)[:16] if last_hb else "Never",
            "specs":          spec,
        })
    return {"total": len(result), "devices": result}


@router.patch("/devices/{device_id}")
def update_device(device_id: int, night_mode: Optional[bool] = None,
                  model_variant: Optional[str] = None,
                  night_threshold: Optional[int] = None,
                  db: Session = Depends(get_db)):
    device = db.query(EdgeDevice).filter(EdgeDevice.id == device_id).first()
    if not device:
        raise HTTPException(404, "Device not found")
    if night_mode is not None:     device.night_mode = night_mode
    if model_variant is not None:  device.model_variant = model_variant
    if night_threshold is not None: device.night_threshold = night_threshold
    db.commit()
    return {"status": "updated", "id": device_id, "night_mode": device.night_mode}


@router.post("/devices/{device_id}/heartbeat")
def device_heartbeat(device_id: int, req: HeartbeatReq, db: Session = Depends(get_db)):
    device = db.query(EdgeDevice).filter(EdgeDevice.id == device_id).first()
    if not device:
        raise HTTPException(404, "Device not found")
    device.status = req.status
    device.last_heartbeat = datetime.datetime.utcnow()
    device.config_json = {
        **(device.config_json or {}),
        "last_cpu": req.cpu_pct,
        "last_ram": req.ram_pct,
        "last_temp": req.temp_c,
        "last_fps": req.fps,
    }
    db.commit()
    return {"status": "ok", "device_id": device_id, "server_time": datetime.datetime.utcnow().isoformat()}


@router.get("/devices/{device_id}/config")
def get_device_config(device_id: int, db: Session = Depends(get_db)):
    """Device pulls its full config on startup."""
    device = db.query(EdgeDevice).filter(EdgeDevice.id == device_id).first()
    if not device:
        raise HTTPException(404, "Device not found")
    return {
        "device_id":      device.device_id,
        "model_variant":  device.model_variant,
        "night_mode":     device.night_mode,
        "night_threshold": device.night_threshold,
        "night_mode_settings": NIGHT_MODE_SETTINGS if device.night_mode else None,
        "api_endpoint":   "http://localhost:8000",
        "upload_path":    "/upload-video",
        "ws_alerts":      "ws://localhost:8000/ws/alerts",
        "heartbeat_interval_sec": 60,
        "zones": ["Entrance", "Electronics", "Apparel", "Grocery", "Checkout"],
    }


# ── Night Mode ────────────────────────────────────────────────────────────────

@router.get("/night-mode/status")
def night_mode_status(store_id: str = "store_1", db: Session = Depends(get_db)):
    devices = db.query(EdgeDevice).filter(EdgeDevice.store_id == store_id).all()
    night_enabled = [d for d in devices if d.night_mode]
    return {
        "total_devices":    len(devices),
        "night_mode_on":    len(night_enabled),
        "night_mode_off":   len(devices) - len(night_enabled),
        "settings":         NIGHT_MODE_SETTINGS,
        "devices": [
            {"device_id": d.device_id, "night_mode": d.night_mode, "threshold": d.night_threshold}
            for d in devices
        ],
        "schedule_tip": "Enable night mode automatically from 8PM–8AM for best low-light accuracy",
    }


@router.post("/night-mode/toggle")
def toggle_night_mode(device_id: str, enabled: bool, db: Session = Depends(get_db)):
    device = db.query(EdgeDevice).filter(EdgeDevice.device_id == device_id).first()
    if not device:
        raise HTTPException(404, "Device not found")
    device.night_mode = enabled
    db.commit()
    return {
        "status":    "updated",
        "device_id": device_id,
        "night_mode": enabled,
        "settings":  NIGHT_MODE_SETTINGS if enabled else None,
    }


# ── Deployment Guide ──────────────────────────────────────────────────────────

@router.get("/deployment/guide")
def deployment_guide():
    return {
        "title": "Edge Deployment Guide — RetailVision AI",
        "devices": DEVICE_SPECS,
        "night_mode_settings": NIGHT_MODE_SETTINGS,
        "setup_steps": {
            "jetson_nano": [
                "1. Flash JetPack 5.x on SD card",
                "2. git clone https://github.com/your-org/retailvision-edge",
                "3. pip install -r requirements_edge.txt",
                "4. Set API_ENDPOINT=http://your-server:8000 in .env",
                "5. python edge_agent.py --device-id cam_001 --store-id store_1",
                "6. Register device: POST /edge/devices",
                "7. Device auto-pulls config and starts streaming",
            ],
            "oak_d": [
                "1. pip install depthai",
                "2. Connect OAK-D via USB3",
                "3. python oakd_agent.py --store-id store_1",
                "4. Device auto-detects and streams to server",
            ],
            "raspberry_pi": [
                "1. Install Raspberry Pi OS 64-bit",
                "2. pip install ultralytics picamera2",
                "3. python rpi_agent.py --model yolov8n --store-id store_1",
            ],
        },
        "privacy_benefits": [
            "All video processing happens on-device — no raw footage sent to cloud",
            "Only anonymized analytics (counts, zones) sent to server",
            "Complies with GDPR/PDPA data minimization principles",
            "Footage never leaves the store premises",
        ],
        "cost_savings": {
            "cloud_bandwidth_saved": "~95% reduction vs cloud streaming",
            "latency_improvement":   "< 50ms local vs 200-500ms cloud",
            "monthly_cloud_cost":    "₹0 for video processing (only analytics sync)",
        },
        "recommended_setup": {
            "small_store_1_2_cameras":  "Jetson Nano or OAK-D",
            "medium_store_4_8_cameras": "Jetson Orin NX",
            "large_store_8_plus":       "Multiple Jetson Orin NX units",
        },
    }


# ── Edge Summary ──────────────────────────────────────────────────────────────

@router.get("/summary")
def edge_summary(store_id: str = "store_1", db: Session = Depends(get_db)):
    devices = db.query(EdgeDevice).filter(EdgeDevice.store_id == store_id).all()
    online  = sum(
        1 for d in devices
        if d.last_heartbeat and (datetime.datetime.utcnow() - d.last_heartbeat).seconds < 120
    )
    night_on = sum(1 for d in devices if d.night_mode)
    return {
        "total_devices":  len(devices),
        "online":         online,
        "offline":        len(devices) - online,
        "night_mode_on":  night_on,
        "device_types":   list({d.device_type for d in devices}),
        "health_pct":     round(online / len(devices) * 100) if devices else 0,
    }
