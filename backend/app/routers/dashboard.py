"""
routers/dashboard.py — SSE Live Dashboard + KPIs for Retail AI
"""
import asyncio
import json
import datetime
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.database.db import SessionLocal
from app.database.models import AnalyticsJob, JobStatus, AlertLog

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _get_live_kpis() -> dict:
    """Pull real data from DB + live camera session metrics."""
    db = SessionLocal()
    try:
        jobs       = db.query(AnalyticsJob).all()
        completed  = [j for j in jobs if j.status == JobStatus.COMPLETED]
        processing = [j for j in jobs if j.status == JobStatus.PROCESSING]
        alerts_all = db.query(AlertLog).all()

        db_entries = 0
        db_exits   = 0
        shelf_empties = 0
        peak_crowd    = 0

        for j in completed:
            r = j.result or {}
            db_entries += r.get("entries", 0)
            db_exits   += r.get("exits",   0)
            pc = r.get("peak_crowd", {})
            if isinstance(pc, dict):
                peak_crowd = max(peak_crowd, pc.get("count", 0))
            if r.get("shelf_status") in ("EMPTY", "LOW STOCK"):
                shelf_empties += 1

        # ── Live RTSP jobs aggregate ──
        try:
            from app.routers.camera import _active_rtsp_jobs
            rtsp_inside  = 0
            rtsp_entries = 0
            rtsp_exits   = 0
            rtsp_unique  = 0
            for jid in list(_active_rtsp_jobs.keys()):
                job = db.query(AnalyticsJob).filter(AnalyticsJob.job_id == jid).first()
                if job and job.result:
                    r = job.result
                    rtsp_inside  += r.get("currently_inside", 0)
                    rtsp_entries += r.get("entries", 0)
                    rtsp_exits   += r.get("exits", 0)
                    rtsp_unique  += r.get("total_unique_people", 0)
        except Exception:
            rtsp_inside = rtsp_entries = rtsp_exits = rtsp_unique = 0

        # ── Live camera session (OAK-D / webcam) ──
        try:
            from app.routers.camera import get_session_snapshot
            cam = get_session_snapshot()
        except Exception:
            cam = {
                "entries": 0, "exits": 0, "currently_inside": 0,
                "peak_count": 0, "unique_people": 0,
                "zone_current": {}, "avg_per_frame": {}, "most_popular": None,
            }

        cam_entries = cam["entries"] + rtsp_entries
        cam_exits   = cam["exits"]   + rtsp_exits
        cam_inside  = cam["currently_inside"] + rtsp_inside
        cam_unique  = cam["unique_people"]    + rtsp_unique
        cam_peak    = max(cam["peak_count"], rtsp_inside)

        total_entries = db_entries + cam_entries
        total_exits   = db_exits   + cam_exits
        peak_crowd    = max(peak_crowd, cam_peak)

        # Zone heatmap — sirf live camera zones, no hardcoded defaults
        zone_current = cam.get("zone_current", {})
        zone_heatmap = dict(zone_current) if zone_current else {}

        # Conversion rate: exits / entries × 100 (live session only)
        conversion = round(cam_exits / cam_entries * 100, 1) if cam_entries > 0 else 0.0

        return {
            "ts":              datetime.datetime.utcnow().isoformat(),
            "total_jobs":      len(jobs),
            "completed_jobs":  len(completed),
            "active_jobs":     len(processing),
            "total_entries":   cam_entries,   # live session only
            "total_exits":     cam_exits,
            "peak_crowd":      cam_peak,
            "shelf_alerts":    shelf_empties,
            "total_alerts":    len(alerts_all),
            "unread_alerts":   len(alerts_all),
            "live_crowd":      cam_inside,
            "total_unique":    cam_unique,
            "conversion_rate": conversion,
            "avg_dwell_min":   0,
            "zone_heatmap":    zone_heatmap,
            "cam_entries":     cam_entries,
            "cam_exits":       cam_exits,
            "cam_inside":      cam_inside,
            "cam_unique":      cam_unique,
            "most_popular_zone": cam.get("most_popular"),
        }
    finally:
        db.close()


@router.get("/stream")
async def sse_stream():
    """SSE endpoint — pushes KPIs every 5 seconds."""
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
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/kpis")
def get_kpis():
    return _get_live_kpis()


@router.get("/notifications")
def get_notifications():
    db = SessionLocal()
    try:
        alerts = db.query(AlertLog).order_by(AlertLog.wall_time.desc()).limit(20).all()
        notifs = [{
            "id":      a.id,
            "type":    a.severity,
            "title":   f"{a.severity} Alert",
            "message": a.message,
            "time":    str(a.wall_time),
            "read":    False,
        } for a in alerts]
        return {"notifications": notifs, "unread": len(notifs)}
    finally:
        db.close()


@router.get("/recent-jobs")
def recent_jobs():
    db = SessionLocal()
    try:
        jobs = db.query(AnalyticsJob).order_by(AnalyticsJob.created_at.desc()).limit(5).all()
        return [{
            "job_id":     j.job_id,
            "filename":   j.filename,
            "status":     j.status,
            "progress":   j.progress,
            "entries":    (j.result or {}).get("entries", 0),
            "exits":      (j.result or {}).get("exits",   0),
            "created_at": str(j.created_at),
        } for j in jobs]
    finally:
        db.close()
