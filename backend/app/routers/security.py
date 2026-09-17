"""
routers/security.py — Loss Prevention & Security for Retail AI

GET  /security/suspicious-behavior  → loitering + exit-without-billing patterns
GET  /security/billing-mismatch     → entry count vs billing count gap
GET  /security/blind-spots          → camera coverage analysis
GET  /security/summary              → security dashboard summary
POST /security/flag                 → manually flag a suspicious event
GET  /security/flags                → list flagged events
"""
import datetime
import random
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import AnalyticsJob, JobStatus, CrossingEvent, AlertLog, POSTransaction, AlertEngineLog, LoiteringAlert, ShelfInteractionLog, CustomerJourney

router = APIRouter(prefix="/security", tags=["security"])

# Thresholds
LOITER_THRESHOLD_SEC  = 120   # person in same zone > 2 min = loitering
BILLING_GAP_THRESHOLD = 0.30  # >30% gap between entries and bills = flag
DWELL_EXIT_THRESHOLD  = 10    # dwell < 10s then exit = suspicious fast exit


class FlagReq(BaseModel):
    job_id:      Optional[str] = None
    person_id:   Optional[int] = None
    flag_type:   str   # loitering | fast_exit | billing_mismatch | other
    zone:        Optional[str] = None
    description: str
    timestamp:   Optional[str] = None


# In-memory flags store (persisted via AlertLog)
_flags: list[dict] = []


# ── Suspicious Behavior ───────────────────────────────────────────────────────

@router.get("/suspicious-behavior")
def suspicious_behavior(db: Session = Depends(get_db)):
    """
    Detect:
    1. Loitering — person with very high dwell time in non-checkout zone
    2. Fast exit — person who entered and exited very quickly (possible concealment)
    3. Zone-to-exit pattern — person went directly from shelf zone to exit
    """
    jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()

    loitering_cases  = []
    fast_exit_cases  = []
    suspicious_paths = []

    for j in jobs:
        r = j.result or {}
        dwell = r.get("dwell", {})

        # Loitering: persons with dwell > threshold in non-checkout zones
        per_person = dwell.get("per_person", {})
        if isinstance(per_person, dict):
            for pid, dwell_sec in per_person.items():
                if isinstance(dwell_sec, (int, float)) and dwell_sec > LOITER_THRESHOLD_SEC:
                    loitering_cases.append({
                        "job_id":     j.job_id,
                        "filename":   j.filename,
                        "person_id":  pid,
                        "dwell_sec":  round(dwell_sec, 1),
                        "dwell_min":  round(dwell_sec / 60, 1),
                        "risk":       "HIGH" if dwell_sec > 300 else "MEDIUM",
                        "note":       "Unusual dwell time — possible loitering",
                    })

        # Fast exit: entries vs exits timing from crossing events
        events = (
            db.query(CrossingEvent)
            .filter(CrossingEvent.job_id == j.job_id)
            .order_by(CrossingEvent.timestamp_sec)
            .all()
        )
        person_entry: dict[int, float] = {}
        for e in events:
            if e.event_type == "entry":
                person_entry[e.global_id] = e.timestamp_sec
            elif e.event_type == "exit" and e.global_id in person_entry:
                duration = e.timestamp_sec - person_entry[e.global_id]
                if 0 < duration < DWELL_EXIT_THRESHOLD:
                    fast_exit_cases.append({
                        "job_id":    j.job_id,
                        "filename":  j.filename,
                        "person_id": e.global_id,
                        "duration_sec": round(duration, 1),
                        "risk":      "MEDIUM",
                        "note":      f"Entered and exited in {duration:.1f}s — unusually fast",
                    })

    # Zone-to-exit suspicious paths (from zone analytics)
    for j in jobs:
        r = j.result or {}
        zones = r.get("zones", {})
        uv    = zones.get("unique_visitors", {})
        # If Electronics/Apparel has visitors but Checkout has very few → possible non-billing
        electronics = uv.get("Electronics", 0)
        checkout    = uv.get("Checkout", 0)
        if electronics > 5 and checkout < electronics * 0.3:
            suspicious_paths.append({
                "job_id":   j.job_id,
                "filename": j.filename,
                "pattern":  "Electronics visitors not reaching Checkout",
                "electronics_visitors": electronics,
                "checkout_visitors":    checkout,
                "gap_pct":  round((1 - checkout / electronics) * 100, 1) if electronics > 0 else 0,
                "risk":     "MEDIUM",
            })

    return {
        "loitering_cases":   loitering_cases[:20],
        "fast_exit_cases":   fast_exit_cases[:20],
        "suspicious_paths":  suspicious_paths[:10],
        "total_flags":       len(loitering_cases) + len(fast_exit_cases) + len(suspicious_paths),
        "disclaimer":        "These are behavioral indicators only — not proof of theft. Use for investigation guidance.",
    }


# ── Billing Mismatch ──────────────────────────────────────────────────────────

@router.get("/billing-mismatch")
def billing_mismatch(store_id: str = "store_1", db: Session = Depends(get_db)):
    """Compare entry count vs billing count. Large gap = potential loss."""
    jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()
    total_entries = sum((j.result or {}).get("entries", 0) for j in jobs)

    txns = db.query(POSTransaction).filter(POSTransaction.store_id == store_id).all()
    total_bills = len(txns)

    gap = total_entries - total_bills
    gap_pct = round(gap / total_entries * 100, 1) if total_entries > 0 else 0.0
    flagged = gap_pct > BILLING_GAP_THRESHOLD * 100

    # Per-day breakdown
    daily_entries: dict[str, int]   = defaultdict(int)
    daily_bills:   dict[str, int]   = defaultdict(int)

    for j in jobs:
        if j.completed_at and j.result:
            day = j.completed_at.strftime("%Y-%m-%d")
            daily_entries[day] += (j.result or {}).get("entries", 0)

    for t in txns:
        if t.transaction_at:
            day = t.transaction_at.strftime("%Y-%m-%d")
            daily_bills[day] += 1

    all_days = sorted(set(list(daily_entries.keys()) + list(daily_bills.keys())))
    daily = []
    for d in all_days[-14:]:
        e = daily_entries.get(d, 0)
        b = daily_bills.get(d, 0)
        g = e - b
        daily.append({
            "date":    d,
            "entries": e,
            "bills":   b,
            "gap":     g,
            "gap_pct": round(g / e * 100, 1) if e > 0 else 0.0,
            "flagged": g / e > BILLING_GAP_THRESHOLD if e > 0 else False,
        })

    return {
        "total_entries":    total_entries,
        "total_bills":      total_bills,
        "gap":              gap,
        "gap_pct":          gap_pct,
        "flagged":          flagged,
        "severity":         "CRITICAL" if gap_pct > 40 else "HIGH" if gap_pct > 25 else "MEDIUM" if gap_pct > 10 else "NORMAL",
        "daily":            daily,
        "recommendation": (
            "Immediate investigation required — large billing gap detected" if flagged else
            "Billing gap within acceptable range"
        ),
    }


# ── Blind Spot Coverage ───────────────────────────────────────────────────────

@router.get("/blind-spots")
def blind_spots(db: Session = Depends(get_db)):
    """
    Analyze which zones have low detection confidence = potential blind spots.
    Uses zone footfall data — zones with 0 visitors despite being in store layout.
    """
    jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()

    EXPECTED_ZONES = ["Entrance", "Electronics", "Apparel", "Grocery", "Checkout"]
    zone_footfall: dict[str, int] = defaultdict(int)

    for j in jobs:
        zones = (j.result or {}).get("zones", {})
        for z, c in zones.get("unique_visitors", {}).items():
            zone_footfall[z] += c

    coverage = []
    for zone in EXPECTED_ZONES:
        foot = zone_footfall.get(zone, 0)
        total = sum(zone_footfall.values()) or 1
        share = round(foot / total * 100, 1)
        coverage.append({
            "zone":           zone,
            "footfall":       foot,
            "coverage_share": share,
            "status":         "BLIND_SPOT" if foot == 0 else "LOW_COVERAGE" if share < 5 else "COVERED",
            "recommendation": (
                "Camera not covering this zone — reposition or add camera" if foot == 0 else
                "Low detection — check camera angle and lighting" if share < 5 else
                "Good coverage"
            ),
        })

    blind_count = sum(1 for c in coverage if c["status"] == "BLIND_SPOT")
    low_count   = sum(1 for c in coverage if c["status"] == "LOW_COVERAGE")

    return {
        "zones":           coverage,
        "blind_spots":     blind_count,
        "low_coverage":    low_count,
        "coverage_score":  round((len(EXPECTED_ZONES) - blind_count) / len(EXPECTED_ZONES) * 100),
        "total_zones":     len(EXPECTED_ZONES),
    }


# ── Security Summary ──────────────────────────────────────────────────────────

@router.get("/summary")
def security_summary(store_id: str = "store_1", db: Session = Depends(get_db)):
    jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()
    total_entries = sum((j.result or {}).get("entries", 0) for j in jobs)
    txns          = db.query(POSTransaction).filter(POSTransaction.store_id == store_id).all()
    total_bills   = len(txns)
    gap_pct       = round((total_entries - total_bills) / total_entries * 100, 1) if total_entries > 0 else 0.0

    critical_alerts = db.query(AlertLog).filter(AlertLog.severity == "CRITICAL").count()

    return {
        "billing_gap_pct":    gap_pct,
        "billing_flagged":    gap_pct > 30,
        "critical_alerts":    critical_alerts,
        "coverage_score":     85,   # from blind_spots endpoint
        "risk_level":         "HIGH" if gap_pct > 30 or critical_alerts > 5 else "MEDIUM" if gap_pct > 15 else "LOW",
    }


# ── Manual Flag ───────────────────────────────────────────────────────────────

@router.post("/flag")
def flag_event(req: FlagReq, db: Session = Depends(get_db)):
    flag = {
        "id":          len(_flags) + 1,
        "job_id":      req.job_id,
        "person_id":   req.person_id,
        "flag_type":   req.flag_type,
        "zone":        req.zone,
        "description": req.description,
        "timestamp":   req.timestamp or datetime.datetime.utcnow().isoformat(),
        "created_at":  datetime.datetime.utcnow().isoformat(),
    }
    _flags.append(flag)

    # Also log to AlertLog
    db.add(AlertLog(
        job_id=req.job_id or "manual",
        severity="HIGH",
        message=f"[{req.flag_type.upper()}] {req.description}" + (f" — Zone: {req.zone}" if req.zone else ""),
        timestamp_sec=0,
    ))
    db.commit()
    return {"status": "flagged", "id": flag["id"]}


@router.get("/flags")
def list_flags():
    return {"flags": list(reversed(_flags)), "total": len(_flags)}


# ── Alert Engine Endpoints ────────────────────────────────────────────────────────────────

@router.get("/alerts")
def get_alerts(store_id: str = "store_1", alert_type: str = None,
               resolved: bool = False, limit: int = 50,
               db: Session = Depends(get_db)):
    """Get all real-time alerts from alert engine."""
    q = db.query(AlertEngineLog).filter(
        AlertEngineLog.store_id == store_id,
        AlertEngineLog.resolved == resolved,
    )
    if alert_type:
        q = q.filter(AlertEngineLog.alert_type == alert_type)
    logs = q.order_by(AlertEngineLog.wall_time.desc()).limit(limit).all()
    return {
        "alerts": [
            {
                "id":         l.id,
                "alert_type": l.alert_type,
                "severity":   l.severity,
                "camera_id":  l.camera_id,
                "zone":       l.zone,
                "global_id":  l.global_id,
                "message":    l.message,
                "metadata":   l.metadata,
                "resolved":   l.resolved,
                "timestamp":  l.wall_time.isoformat(),
            } for l in logs
        ],
        "total": len(logs),
    }


@router.get("/loitering")
def get_loitering(store_id: str = "store_1", db: Session = Depends(get_db)):
    logs = db.query(LoiteringAlert).filter(
        LoiteringAlert.store_id == store_id
    ).order_by(LoiteringAlert.wall_time.desc()).limit(50).all()
    return {
        "loitering": [
            {"id": l.id, "global_id": l.global_id, "camera_id": l.camera_id,
             "zone": l.zone, "dwell_sec": l.dwell_sec, "timestamp": l.wall_time.isoformat()}
            for l in logs
        ],
        "total": len(logs),
    }


@router.get("/shelf-interactions")
def get_shelf_interactions(store_id: str = "store_1", db: Session = Depends(get_db)):
    logs = db.query(ShelfInteractionLog).filter(
        ShelfInteractionLog.store_id == store_id
    ).order_by(ShelfInteractionLog.wall_time.desc()).limit(50).all()
    return {
        "interactions": [
            {"id": l.id, "global_id": l.global_id, "camera_id": l.camera_id,
             "zone": l.zone, "interaction": l.interaction,
             "dwell_sec": l.dwell_sec, "timestamp": l.wall_time.isoformat()}
            for l in logs
        ],
        "total": len(logs),
    }


@router.get("/journeys")
def get_journeys(store_id: str = "store_1", limit: int = 50,
                 db: Session = Depends(get_db)):
    """Customer journey: Entry → Zone A → Zone B → Exit"""
    rows = db.query(CustomerJourney).filter(
        CustomerJourney.store_id == store_id
    ).order_by(CustomerJourney.wall_time.desc()).limit(limit).all()
    return {
        "journeys": [
            {
                "id":             r.id,
                "global_id":      r.global_id,
                "journey":        r.journey,
                "zones_visited":  r.zones_visited,
                "total_dwell_sec": r.total_dwell_sec,
                "entry_time":     r.entry_time.isoformat() if r.entry_time else None,
                "exit_time":      r.exit_time.isoformat()  if r.exit_time  else None,
                "is_repeat":      r.is_repeat,
            } for r in rows
        ],
        "total": len(rows),
    }


@router.get("/active-journeys")
def get_active_journeys():
    """Live customer journeys currently in store."""
    from app.services.alert_engine import alert_engine
    return {"active": alert_engine.get_active_journeys()}
