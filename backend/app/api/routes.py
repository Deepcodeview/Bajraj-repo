"""
routes.py — FastAPI routes for the Retail AI backend.

Endpoints:
  GET  /                          Health check
  POST /upload-video/             Upload video (saves file, waits for config)
  GET  /jobs/{job_id}/frame       Get first frame as JPEG for zone editor
  POST /jobs/{job_id}/start       Start processing with custom zones + line
  GET  /result/{job_id}           Poll job status + get analytics when done
  GET  /jobs/                     List all jobs
  GET  /jobs/{job_id}/crossings   Per-person entry/exit crossing log
  GET  /jobs/{job_id}/video       Stream the annotated output video
  DELETE /jobs/{job_id}           Delete a job record + files
"""

import os
import uuid
import logging
import threading
import datetime
import json
import cv2
import numpy as np
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session
import queue
from app.utils.streamer import frame_streamer

from app.config import UPLOAD_DIR, OUTPUT_DIR
from app.database.db import get_db
from app.database.models import AnalyticsJob, CrossingEvent, JobStatus, AlertLog
from app.services.analytics_service import process_video
from app.schemas.response import UploadResponse, JobStatusResponse, AllJobsResponse

log = logging.getLogger(__name__)
router = APIRouter()


# ── Health ────────────────────────────────────────────────────────────────────
@router.get("/")
def home():
    return {"message": "Retail AI Backend Running 🚀", "status": "ok"}


@router.get("/health")
def health():
    return {"status": "ok", "message": "Retail AI Backend is running"}


@router.get("/events")
async def events():
    """Alias → /dashboard/stream (SSE live KPIs)"""
    from app.routers.dashboard import _get_live_kpis
    import asyncio, json
    from fastapi.responses import StreamingResponse

    async def generator():
        while True:
            try:
                data = _get_live_kpis()
                yield f"data: {json.dumps(data)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/analytics")
def analytics():
    """Alias → /dashboard/kpis"""
    from app.routers.dashboard import _get_live_kpis
    return _get_live_kpis()


@router.get("/persons")
def persons():
    """Alias → /camera/tracking/active"""
    from app.reid.global_registry import global_registry
    from app.routers.camera import ALL_CAMERAS
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


# ── Upload & process ──────────────────────────────────────────────────────────
@router.post("/upload-video/", response_model=UploadResponse)
async def upload_video(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # Validate file type
    if not file.filename.lower().endswith((".mp4", ".avi", ".mov", ".mkv", ".webm")):
        raise HTTPException(400, "Unsupported file type. Use MP4, AVI, MOV, MKV, or WebM.")

    job_id = str(uuid.uuid4())
    safe_name = f"{job_id}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)

    # Save upload (chunked to avoid loading entire file into memory)
    try:
        with open(file_path, "wb") as buf:
            while chunk := await file.read(1024 * 1024):  # 1 MB chunks
                buf.write(chunk)
    except Exception as e:
        raise HTTPException(500, f"Failed to save upload: {e}")

    # Create DB record
    job = AnalyticsJob(
        job_id=job_id,
        filename=file.filename,
        status=JobStatus.QUEUED,
        progress=0,
    )
    db.add(job)
    db.commit()

    # Don't start processing yet — wait for user to configure zones
    return UploadResponse(
        status="queued",
        job_id=job_id,
        message=f"Video '{file.filename}' uploaded. Configure zones then POST /jobs/{job_id}/start",
    )


# ── Get first frame for zone editor ──────────────────────────────────────────
@router.get("/jobs/{job_id}/frame")
def get_first_frame(job_id: str, db: Session = Depends(get_db)):
    job = db.query(AnalyticsJob).filter(AnalyticsJob.job_id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found.")

    # Find uploaded file
    file_path = None
    for f in os.listdir(UPLOAD_DIR):
        if f.startswith(job_id):
            file_path = os.path.join(UPLOAD_DIR, f)
            break
    if not file_path:
        raise HTTPException(404, "Video file not found.")

    cap = cv2.VideoCapture(file_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 15)
    ret, frame = cap.read()
    if not ret or frame is None:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        raise HTTPException(500, "Could not read preview frame.")

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return Response(content=buf.tobytes(), media_type="image/jpeg")


# ── Start Live Camera Monitoring ──────────────────────────────────────────────
@router.post("/jobs/camera/start")
def start_camera_monitoring(
    camera_source: str = Form("0"),  # "0" for webcam, or RTSP URL
    zones: str = Form(...),
    entry_zone: str = Form(default="[]"),
    exit_zone: str  = Form(default="[]"),
    conf: float = Form(0.35),
    db: Session = Depends(get_db),
):
    try:
        zones_data     = json.loads(zones)
        entry_zone_pts = json.loads(entry_zone)
        exit_zone_pts  = json.loads(exit_zone)
    except Exception:
        raise HTTPException(400, "Invalid JSON in zones/entry_zone/exit_zone.")

    job_id = str(uuid.uuid4())
    filename = "Live Camera" if camera_source == "0" else f"Stream ({camera_source})"

    job = AnalyticsJob(
        job_id=job_id,
        filename=filename,
        status=JobStatus.PROCESSING,
        progress=0,
    )
    db.add(job)
    db.commit()

    thread = threading.Thread(
        target=_run_analysis,
        args=(camera_source, job_id, zones_data, entry_zone_pts, exit_zone_pts, conf),
        daemon=True,
    )
    thread.start()

    return {"status": "processing", "job_id": job_id}


# ── Get Camera Preview Frame ──────────────────────────────────────────────────
@router.post("/jobs/camera/preview-frame")
def get_camera_preview_frame(camera_source: str = Form("0")):
    frame = None
    ret = False
    if camera_source == "oak":
        try:
            import depthai as dai
            pipeline = dai.Pipeline()
            cam = pipeline.createColorCamera()
            cam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
            cam.setFps(30)
            cam.setInterleaved(False)
            cam.setBoardSocket(dai.CameraBoardSocket.CAM_A)
            cam.initialControl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.CONTINUOUS_VIDEO)

            xout = pipeline.createXLinkOut()
            xout.setStreamName("video")
            cam.video.link(xout.input)

            with dai.Device(pipeline) as device:
                q = device.getOutputQueue("video", maxSize=4, blocking=False)
                frame = q.get().getCvFrame()
                ret = True
        except Exception as e:
            raise HTTPException(500, f"Could not capture preview frame from OAK camera: {e}")
    else:
        try:
            source = int(camera_source)
        except ValueError:
            source = camera_source
        
        cap = cv2.VideoCapture(source)
        ret, frame = cap.read()
        cap.release()
    
    if not ret or frame is None:
        raise HTTPException(500, "Could not capture preview frame from camera.")
    
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return Response(content=buf.tobytes(), media_type="image/jpeg")


# ── Start processing with custom config ──────────────────────────────────────
@router.post("/jobs/{job_id}/start")
def start_processing(
    job_id: str,
    zones: str = Form(...),
    entry_zone: str = Form(default="[]"),
    exit_zone: str  = Form(default="[]"),
    conf: float = Form(0.35),
    db: Session = Depends(get_db),
):
    job = db.query(AnalyticsJob).filter(AnalyticsJob.job_id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found.")
    if job.status not in (JobStatus.QUEUED,):
        raise HTTPException(400, f"Job already {job.status}, cannot restart.")

    try:
        zones_data     = json.loads(zones)
        entry_zone_pts = json.loads(entry_zone)   # list of [x, y]
        exit_zone_pts  = json.loads(exit_zone)
    except Exception:
        raise HTTPException(400, "Invalid JSON in zones/entry_zone/exit_zone.")

    # Find uploaded file
    file_path = None
    for f in os.listdir(UPLOAD_DIR):
        if f.startswith(job_id):
            file_path = os.path.join(UPLOAD_DIR, f)
            break
    if not file_path:
        raise HTTPException(404, "Video file not found.")

    job.status = JobStatus.PROCESSING
    db.commit()

    thread = threading.Thread(
        target=_run_analysis,
        args=(file_path, job_id, zones_data, entry_zone_pts, exit_zone_pts, conf),
        daemon=True,
    )
    thread.start()

    return {"status": "processing", "job_id": job_id}


# ── Live MJPEG Stream ─────────────────────────────────────────────────────────
@router.get("/jobs/{job_id}/stream")
@router.head("/jobs/{job_id}/stream")
def get_live_stream(job_id: str):
    q = frame_streamer.register(job_id)

    def generator():
        empty_count = 0
        try:
            while True:
                try:
                    frame_bytes = q.get(timeout=2.0)
                    empty_count = 0
                except queue.Empty:
                    empty_count += 1
                    # Keep stream alive for up to 60s with no frames
                    if empty_count > 30:
                        break
                    continue
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )
        finally:
            frame_streamer.unregister(job_id, q)

    return StreamingResponse(
        generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )



# ── Poll result ───────────────────────────────────────────────────────────────
@router.get("/result/{job_id}", response_model=JobStatusResponse)
def get_result(job_id: str, db: Session = Depends(get_db)):
    job = db.query(AnalyticsJob).filter(AnalyticsJob.job_id == job_id).first()
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found.")

    # Always return live analytics if available (updated every 30 frames during processing)
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        analytics=job.result,   # live metrics during processing, final after completion
    )


# ── List all jobs ─────────────────────────────────────────────────────────────
@router.get("/jobs/", response_model=AllJobsResponse)
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(AnalyticsJob).order_by(AnalyticsJob.created_at.desc()).all()
    return AllJobsResponse(
        total=len(jobs),
        jobs=[
            {
                "job_id":       j.job_id,
                "filename":     j.filename,
                "status":       j.status,
                "progress":     j.progress,
                "created_at":   str(j.created_at),
                "completed_at": str(j.completed_at) if j.completed_at else None,
            }
            for j in jobs
        ],
    )


# ── Crossing log ──────────────────────────────────────────────────────────────
@router.get("/jobs/{job_id}/crossings")
def get_crossings(job_id: str, db: Session = Depends(get_db)):
    job = db.query(AnalyticsJob).filter(AnalyticsJob.job_id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found.")
    if job.status not in (JobStatus.COMPLETED, JobStatus.PROCESSING):
        raise HTTPException(400, f"Job is not active or completed (status: {job.status}).")

    events = (
        db.query(CrossingEvent)
        .filter(CrossingEvent.job_id == job_id)
        .order_by(CrossingEvent.timestamp_sec)
        .all()
    )
    return {
        "job_id": job_id,
        "total_crossings": len(events),
        "events": [
            {
                "id":            e.id,
                "global_id":     e.global_id,
                "event_type":    e.event_type,
                "timestamp_sec": e.timestamp_sec,
                "wall_time":     str(e.wall_time),
            }
            for e in events
        ],
    }


# ── Alert log ─────────────────────────────────────────────────────────────────
@router.get("/jobs/{job_id}/alerts")
def get_alerts(job_id: str, db: Session = Depends(get_db)):
    job = db.query(AnalyticsJob).filter(AnalyticsJob.job_id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found.")

    alerts = (
        db.query(AlertLog)
        .filter(AlertLog.job_id == job_id)
        .order_by(AlertLog.timestamp_sec.desc())
        .all()
    )
    return {
        "job_id": job_id,
        "total_alerts": len(alerts),
        "alerts": [
            {
                "id":            a.id,
                "severity":      a.severity,
                "message":       a.message,
                "timestamp_sec": a.timestamp_sec,
                "wall_time":     str(a.wall_time),
            }
            for a in alerts
        ],
    }


# ── AI Store Health Report ────────────────────────────────────────────────────
@router.post("/jobs/{job_id}/ai-report")
def generate_ai_report(job_id: str, db: Session = Depends(get_db)):
    job = db.query(AnalyticsJob).filter(AnalyticsJob.job_id == job_id).first()
    if not job or not job.result:
        raise HTTPException(404, "Job or analytics results not found.")
    
    res = job.result
    
    report_en = f"🏪 Smart Store Performance Insights:\n\n1. Visitor Traffic: A total of {res.get('entries', 0)} entries and {res.get('exits', 0)} exits were recorded. The peak crowd reached {res.get('peak_crowd', {}).get('count', 0)} shoppers simultaneously.\n2. Zone Dwell Analysis: Zone '{res.get('zones', {}).get('most_popular', 'N/A')}' was the most popular zone with the highest unique visitors. Dwell times indicate interest in shelf items.\n3. Shelf Stock Audit: Shelf status final state is '{res.get('shelf_status', 'NORMAL')}'."
    if res.get('shelf_status') == 'EMPTY':
         report_en += "\n⚠️ ACTION REQUIRED: Shelf is empty! Restock immediately to prevent sales loss."
    elif res.get('shelf_status') == 'LOW STOCK':
         report_en += "\nℹ️ recommendation: Shelf stock is low. Replenish items soon."
    
    report_hi = f"🏪 स्मार्ट स्टोर प्रदर्शन अंतर्दृष्टि:\n\n1. ग्राहक आवागमन: कुल {res.get('entries', 0)} प्रवेश और {res.get('exits', 0)} निकास दर्ज किए गए। एक समय पर अधिकतम भीड़ {res.get('peak_crowd', {}).get('count', 0)} ग्राहकों की थी।\n2. लोकप्रिय क्षेत्र (Zone): सबसे अधिक भीड़ '{res.get('zones', {}).get('most_popular', 'N/A')}' क्षेत्र में रही। ग्राहकों ने वहां अधिक समय बिताया।\n3. शेल्फ स्टॉक स्थिति: मुख्य रूप से शेल्फ स्टॉक '{res.get('shelf_status', 'NORMAL')}' रहा।"
    if res.get('shelf_status') == 'EMPTY':
         report_hi += "\n⚠️ तत्काल कार्रवाई: शेल्फ खाली है! बिक्री नुकसान से बचने के लिए तुरंत सामान भरें।"
    elif res.get('shelf_status') == 'LOW STOCK':
         report_hi += "\nℹ️ सुझाव: शेल्फ में सामान कम है। जल्द ही सामान भरने की योजना बनाएं।"

    return {
        "job_id": job_id,
        "report_en": report_en,
        "report_hi": report_hi
    }



# ── Annotated video download ──────────────────────────────────────────────────
@router.get("/jobs/{job_id}/video")
def get_annotated_video(job_id: str, db: Session = Depends(get_db)):
    job = db.query(AnalyticsJob).filter(AnalyticsJob.job_id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found.")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(400, "Job not completed yet.")

    video_path = os.path.join(OUTPUT_DIR, f"{job_id}_annotated.mp4")
    if not os.path.exists(video_path):
        raise HTTPException(404, "Annotated video not found (may have been deleted or disabled).")

    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=f"annotated_{job_id}.mp4",
    )


# ── Delete job ────────────────────────────────────────────────────────────────
@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(AnalyticsJob).filter(AnalyticsJob.job_id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found.")

    # Clean up DB
    db.query(CrossingEvent).filter(CrossingEvent.job_id == job_id).delete()
    db.delete(job)
    db.commit()

    # Clean up files (best-effort)
    for folder in [UPLOAD_DIR, OUTPUT_DIR]:
        for f in os.listdir(folder):
            if f.startswith(job_id):
                try:
                    os.remove(os.path.join(folder, f))
                except OSError:
                    pass

    return {"status": "deleted", "job_id": job_id}


# ── Background worker ─────────────────────────────────────────────────────────
def _run_analysis(file_path: str, job_id: str, zones_data: list = None,
                  entry_zone_data: list = None, exit_zone_data: list = None,
                  conf: float = 0.35, mode: str = "indoor", dataset_rtsp_url: str = "",
                  camera_id: str = "unknown", camera_name: str = "",
                  stop_event: threading.Event = None) -> None:
    """Runs in a daemon thread. Updates DB throughout processing."""
    from app.database.db import SessionLocal

    db = SessionLocal()
    try:
        job = db.query(AnalyticsJob).filter(AnalyticsJob.job_id == job_id).first()
        if not job:
            log.error(f"[{job_id}] Job record missing from DB.")
            return

        def progress_cb(pct: int, live_analytics: dict = None, alert: dict = None):
            progress_db = SessionLocal()
            try:
                j = progress_db.query(AnalyticsJob).filter(AnalyticsJob.job_id == job_id).first()
                if j:
                    j.progress = pct
                    if live_analytics:
                        j.result = live_analytics
                    progress_db.commit()
            except Exception:
                progress_db.rollback()
            finally:
                progress_db.close()

        analytics = process_video(
            file_path,
            job_id=job_id,
            progress_cb=progress_cb,
            zones_data=zones_data,
            entry_zone_data=entry_zone_data,
            exit_zone_data=exit_zone_data,
            conf=conf,
            mode=mode,
            dataset_rtsp_url=dataset_rtsp_url,
            camera_id=camera_id,
            camera_name=camera_name,
            stop_event=stop_event,
        )

        is_rtsp = isinstance(file_path, str) and file_path.startswith("rtsp://")
        if not is_rtsp:
            # Only mark completed for file-based jobs
            analytics.pop("crossing_log", None)
            job = db.query(AnalyticsJob).filter(AnalyticsJob.job_id == job_id).first()
            job.status       = JobStatus.COMPLETED
            job.progress     = 100
            job.result       = analytics
            job.completed_at = datetime.datetime.utcnow()
            db.commit()
            log.info(f"[{job_id}] Job completed successfully.")
        else:
            log.info(f"[{job_id}] RTSP stream ended.")
            try:
                job = db.query(AnalyticsJob).filter(AnalyticsJob.job_id == job_id).first()
                if job and job.status == JobStatus.PROCESSING:
                    job.status       = JobStatus.COMPLETED
                    job.completed_at = datetime.datetime.utcnow()
                    job.progress     = 100
                    db.commit()
            except Exception:
                pass

    except Exception as exc:
        log.exception(f"[{job_id}] Processing failed: {exc}")
        try:
            job = db.query(AnalyticsJob).filter(AnalyticsJob.job_id == job_id).first()
            if job:
                job.status        = JobStatus.FAILED
                job.error_message = str(exc)
                db.commit()
        except Exception:
            pass
    finally:
        try:
            from app.routers.camera import _camera_active_jobs, _job_stop_events, _active_rtsp_jobs
            _active_rtsp_jobs.pop(job_id, None)
            _job_stop_events.pop(job_id, None)
            if camera_id in _camera_active_jobs and _camera_active_jobs[camera_id] == job_id:
                _camera_active_jobs.pop(camera_id, None)
        except Exception:
            pass
        db.close()