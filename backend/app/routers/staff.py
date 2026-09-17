"""
routers/staff.py — Staff & Operations for Retail AI

POST /staff/log-activity         → log staff zone activity
GET  /staff/productivity         → staff productivity vs customer load per zone
GET  /staff/shift-optimization   → recommended staffing levels by hour/day
GET  /staff/self-checkout        → self-checkout error/assistance detection
GET  /staff/summary              → staff ops summary
"""
import datetime
import statistics
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import AnalyticsJob, JobStatus, StaffZoneLog

router = APIRouter(prefix="/staff", tags=["staff"])

# In-memory self-checkout events
_checkout_events: list[dict] = []

HOURS_LABEL = [f"{h:02d}:00" for h in range(24)]
DAYS_OF_WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class StaffActivityReq(BaseModel):
    store_id:    str = "store_1"
    staff_id:    str
    zone:        str
    duration_min: float
    shift_date:  Optional[str] = None


class CheckoutEventReq(BaseModel):
    counter_id:  str
    event_type:  str   # error | assistance_needed | completed | abandoned
    duration_sec: Optional[float] = None
    note:        Optional[str] = None


# ── Log Staff Activity ────────────────────────────────────────────────────────

@router.post("/log-activity")
def log_staff_activity(req: StaffActivityReq, db: Session = Depends(get_db)):
    shift_dt = (
        datetime.datetime.fromisoformat(req.shift_date)
        if req.shift_date else datetime.datetime.utcnow()
    )
    log = StaffZoneLog(
        store_id=req.store_id,
        staff_id=req.staff_id,
        zone=req.zone,
        duration_min=req.duration_min,
        shift_date=shift_dt,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return {"status": "logged", "id": log.id}


# ── Staff Productivity ────────────────────────────────────────────────────────

@router.get("/productivity")
def staff_productivity(store_id: str = "store_1", db: Session = Depends(get_db)):
    """
    Compare staff time in each zone vs customer footfall in that zone.
    High footfall + low staff time = understaffed.
    Low footfall + high staff time = overstaffed.
    """
    logs = db.query(StaffZoneLog).filter(StaffZoneLog.store_id == store_id).all()

    # Staff time per zone
    staff_time: dict[str, float] = defaultdict(float)
    staff_count: dict[str, set]  = defaultdict(set)
    for log in logs:
        if log.zone:
            staff_time[log.zone]  += log.duration_min
            staff_count[log.zone].add(log.staff_id)

    # Customer footfall per zone
    jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()
    zone_footfall: dict[str, int] = defaultdict(int)
    for j in jobs:
        zones = (j.result or {}).get("zones", {})
        for z, c in zones.get("unique_visitors", {}).items():
            zone_footfall[z] += c

    all_zones = set(list(staff_time.keys()) + list(zone_footfall.keys()))
    result = []
    for zone in all_zones:
        s_time = staff_time.get(zone, 0)
        foot   = zone_footfall.get(zone, 0)
        ratio  = round(s_time / foot, 2) if foot > 0 else None
        status = (
            "UNDERSTAFFED" if foot > 50 and s_time < 30 else
            "OVERSTAFFED"  if foot < 10 and s_time > 60 else
            "OPTIMAL"
        )
        result.append({
            "zone":              zone,
            "staff_time_min":    round(s_time, 1),
            "unique_staff":      len(staff_count.get(zone, set())),
            "customer_footfall": foot,
            "staff_per_visitor": ratio,
            "status":            status,
            "recommendation": (
                f"Add staff to {zone} — high customer load, low coverage" if status == "UNDERSTAFFED" else
                f"Reduce staff in {zone} — low customer traffic" if status == "OVERSTAFFED" else
                "Staffing looks balanced"
            ),
        })

    result.sort(key=lambda x: -(x["customer_footfall"] or 0))
    return {
        "zones":              result,
        "total_staff_logged": len({log.staff_id for log in logs}),
        "privacy_note":       "Staff tracking requires explicit consent per local labor laws.",
    }


# ── Shift Optimization ────────────────────────────────────────────────────────

@router.get("/shift-optimization")
def shift_optimization(db: Session = Depends(get_db)):
    """
    Recommend staffing levels by hour and day-of-week based on footfall patterns.
    Rule: 1 staff per 15 customers/hour, minimum 2 staff always.
    """
    jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()

    # Aggregate footfall by hour-of-day and day-of-week
    hourly_footfall: dict[int, list] = defaultdict(list)
    dow_footfall:    dict[int, list] = defaultdict(list)

    for j in jobs:
        if not j.completed_at or not j.result:
            continue
        entries = (j.result or {}).get("entries", 0)
        hour    = j.completed_at.hour
        dow     = j.completed_at.weekday()
        hourly_footfall[hour].append(entries)
        dow_footfall[dow].append(entries)

    # Hourly recommendations
    hourly = []
    for h in range(24):
        vals    = hourly_footfall.get(h, [0])
        avg_ff  = round(statistics.mean(vals), 1)
        staff   = max(2, math.ceil(avg_ff / 15))
        peak    = avg_ff > statistics.mean([statistics.mean(v) for v in hourly_footfall.values()]) * 1.3 if hourly_footfall else False
        hourly.append({
            "hour":              h,
            "label":             HOURS_LABEL[h],
            "avg_footfall":      avg_ff,
            "recommended_staff": staff,
            "is_peak":           peak,
        })

    # Day-of-week recommendations
    dow_recs = []
    for d in range(7):
        vals   = dow_footfall.get(d, [0])
        avg_ff = round(statistics.mean(vals), 1)
        staff  = max(2, math.ceil(avg_ff / 12))
        dow_recs.append({
            "day":               DAYS_OF_WEEK[d],
            "avg_footfall":      avg_ff,
            "recommended_staff": staff,
            "is_peak":           d >= 5,  # Weekend always peak
        })

    peak_hours = [h for h in hourly if h["is_peak"]]
    peak_days  = [d for d in dow_recs if d["is_peak"]]

    return {
        "hourly":          hourly,
        "by_day":          dow_recs,
        "peak_hours":      peak_hours,
        "peak_days":       peak_days,
        "min_staff":       2,
        "staff_per_customers": 15,
        "insight":         f"Peak hours: {', '.join(h['label'] for h in peak_hours[:3])}. Schedule extra staff during these windows.",
    }


# ── Self-Checkout Monitoring ──────────────────────────────────────────────────

@router.post("/self-checkout/event")
def log_checkout_event(req: CheckoutEventReq):
    ev = {
        "id":           len(_checkout_events) + 1,
        "counter_id":   req.counter_id,
        "event_type":   req.event_type,
        "duration_sec": req.duration_sec,
        "note":         req.note,
        "timestamp":    datetime.datetime.utcnow().isoformat(),
    }
    _checkout_events.append(ev)
    return {"status": "logged", "id": ev["id"]}


@router.get("/self-checkout")
def self_checkout_status():
    """Analyze self-checkout error rates and assistance needs."""
    if not _checkout_events:
        return {
            "total_events":    0,
            "error_rate":      0.0,
            "assistance_rate": 0.0,
            "counters":        [],
            "recent_events":   [],
            "status":          "NO_DATA",
        }

    total      = len(_checkout_events)
    errors     = [e for e in _checkout_events if e["event_type"] == "error"]
    assistance = [e for e in _checkout_events if e["event_type"] == "assistance_needed"]
    completed  = [e for e in _checkout_events if e["event_type"] == "completed"]

    error_rate      = round(len(errors) / total * 100, 1)
    assistance_rate = round(len(assistance) / total * 100, 1)

    # Per-counter stats
    counter_stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "errors": 0, "assistance": 0})
    for e in _checkout_events:
        cid = e["counter_id"]
        counter_stats[cid]["total"] += 1
        if e["event_type"] == "error":
            counter_stats[cid]["errors"] += 1
        elif e["event_type"] == "assistance_needed":
            counter_stats[cid]["assistance"] += 1

    counters = [
        {
            "counter_id":       cid,
            "total":            s["total"],
            "errors":           s["errors"],
            "assistance":       s["assistance"],
            "error_rate":       round(s["errors"] / s["total"] * 100, 1),
            "status":           "NEEDS_ATTENTION" if s["errors"] / s["total"] > 0.2 else "OK",
        }
        for cid, s in counter_stats.items()
    ]

    return {
        "total_events":    total,
        "completed":       len(completed),
        "errors":          len(errors),
        "assistance":      len(assistance),
        "error_rate":      error_rate,
        "assistance_rate": assistance_rate,
        "counters":        counters,
        "recent_events":   list(reversed(_checkout_events[-10:])),
        "status":          "CRITICAL" if error_rate > 20 else "WARNING" if error_rate > 10 else "OK",
        "recommendation":  (
            "High error rate — check scanner calibration and UI flow" if error_rate > 20 else
            "Moderate errors — consider staff assistance nearby" if error_rate > 10 else
            "Self-checkout operating normally"
        ),
    }


# ── Staff Summary ─────────────────────────────────────────────────────────────

@router.get("/summary")
def staff_summary(store_id: str = "store_1", db: Session = Depends(get_db)):
    logs = db.query(StaffZoneLog).filter(StaffZoneLog.store_id == store_id).all()
    total_staff  = len({log.staff_id for log in logs})
    total_time   = sum(log.duration_min for log in logs)
    checkout_err = sum(1 for e in _checkout_events if e["event_type"] == "error")
    return {
        "total_staff_logged":    total_staff,
        "total_staff_time_min":  round(total_time, 1),
        "self_checkout_errors":  checkout_err,
        "self_checkout_total":   len(_checkout_events),
        "error_rate":            round(checkout_err / len(_checkout_events) * 100, 1) if _checkout_events else 0.0,
    }
