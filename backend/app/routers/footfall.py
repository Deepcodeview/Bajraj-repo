"""
routers/footfall.py — Footfall data API for Node.js to query
GET /footfall/today          → today's totals per camera
GET /footfall/current        → latest currently_inside per camera
GET /footfall/range          → totals for a date range
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database.db import get_db
from app.database.models import FootfallLog

router = APIRouter(prefix="/footfall", tags=["footfall"])


@router.get("/today")
def footfall_today(store_id: str = "store_1", db: Session = Depends(get_db)):
    """Max entries/exits/total_unique per camera for today, plus latest currently_inside."""
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")

    rows = db.query(FootfallLog).filter(
        FootfallLog.log_date == today,
        FootfallLog.store_id == store_id,
    ).all()

    if not rows:
        return {"date": today, "total_entries": 0, "total_unique": 0,
                "currently_inside": 0, "cameras": []}

    # Per camera: max entries (cumulative peak), latest currently_inside
    cam_map: dict = {}
    for r in rows:
        c = r.camera_id
        if c not in cam_map:
            cam_map[c] = {"entries": 0, "exits": 0, "total_unique": 0,
                          "currently_inside": 0, "last_time": None}
        cam_map[c]["entries"]    = max(cam_map[c]["entries"],    r.entries)
        cam_map[c]["exits"]      = max(cam_map[c]["exits"],      r.exits)
        cam_map[c]["total_unique"] = max(cam_map[c]["total_unique"], r.total_unique)
        if cam_map[c]["last_time"] is None or r.wall_time > cam_map[c]["last_time"]:
            cam_map[c]["currently_inside"] = r.currently_inside
            cam_map[c]["last_time"] = r.wall_time

    cameras = [{"camera_id": k, **{f: v[f] for f in ("entries","exits","total_unique","currently_inside")}}
               for k, v in cam_map.items()]

    return {
        "date":             today,
        "total_entries":    sum(c["entries"]    for c in cameras),
        "total_exits":      sum(c["exits"]      for c in cameras),
        "total_unique":     sum(c["total_unique"] for c in cameras),
        "currently_inside": sum(c["currently_inside"] for c in cameras),
        "cameras":          cameras,
    }


@router.get("/current")
def footfall_current(store_id: str = "store_1", db: Session = Depends(get_db)):
    """Latest currently_inside snapshot across all cameras."""
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")

    # Latest row per camera for today
    subq = (
        db.query(FootfallLog.camera_id, func.max(FootfallLog.wall_time).label("latest"))
        .filter(FootfallLog.log_date == today, FootfallLog.store_id == store_id)
        .group_by(FootfallLog.camera_id)
        .subquery()
    )
    rows = (
        db.query(FootfallLog)
        .join(subq, (FootfallLog.camera_id == subq.c.camera_id) &
                    (FootfallLog.wall_time == subq.c.latest))
        .all()
    )

    total = sum(r.currently_inside for r in rows)
    return {
        "currently_inside": total,
        "cameras": [{"camera_id": r.camera_id, "currently_inside": r.currently_inside}
                    for r in rows],
    }


@router.get("/range")
def footfall_range(
    start_date: str = Query(...),
    end_date:   str = Query(...),
    store_id:   str = "store_1",
    db: Session = Depends(get_db),
):
    """Daily footfall totals between start_date and end_date (YYYY-MM-DD)."""
    rows = db.query(FootfallLog).filter(
        FootfallLog.log_date >= start_date,
        FootfallLog.log_date <= end_date,
        FootfallLog.store_id == store_id,
    ).all()

    # Group by date, take max entries per camera per day then sum cameras
    day_cam: dict = {}
    for r in rows:
        key = (r.log_date, r.camera_id)
        if key not in day_cam:
            day_cam[key] = {"entries": 0, "total_unique": 0}
        day_cam[key]["entries"]     = max(day_cam[key]["entries"],     r.entries)
        day_cam[key]["total_unique"] = max(day_cam[key]["total_unique"], r.total_unique)

    day_totals: dict = {}
    for (date, cam), vals in day_cam.items():
        if date not in day_totals:
            day_totals[date] = {"entries": 0, "total_unique": 0}
        day_totals[date]["entries"]     += vals["entries"]
        day_totals[date]["total_unique"] += vals["total_unique"]

    return {
        "start_date": start_date,
        "end_date":   end_date,
        "daily": [{"date": d, **v} for d, v in sorted(day_totals.items())],
    }
