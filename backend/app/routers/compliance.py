"""
routers/compliance.py — Compliance & Safety for Retail AI

GET  /compliance/occupancy          → current occupancy vs max capacity
POST /compliance/occupancy/log      → log occupancy reading
GET  /compliance/aisle-blockage     → aisle/exit blockage flags
POST /compliance/aisle-blockage/flag → report a blockage
GET  /compliance/cctv-retention     → CCTV footage retention policy status
POST /compliance/cctv-retention/run → run auto-delete based on retention policy
GET  /compliance/summary            → compliance dashboard summary
"""
import datetime
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import AnalyticsJob, JobStatus, OccupancyEvent, AlertLog

router = APIRouter(prefix="/compliance", tags=["compliance"])

# In-memory blockage flags
_blockage_flags: list[dict] = []

# Default zone capacities (configurable)
ZONE_CAPACITY = {
    "Entrance":    30,
    "Electronics": 25,
    "Apparel":     20,
    "Grocery":     40,
    "Checkout":    15,
    "store":       150,  # whole store
}

# CCTV retention policy (days)
DEFAULT_RETENTION_DAYS = 30


class OccupancyLogReq(BaseModel):
    store_id:     str = "store_1"
    zone:         str = "store"
    count:        int
    max_capacity: Optional[int] = None


class BlockageFlagReq(BaseModel):
    zone:        str
    location:    str   # "Fire Exit A", "Aisle 3", etc.
    blocked_by:  str   # "boxes", "trolley", "person", "other"
    severity:    str = "HIGH"
    description: Optional[str] = None


class RetentionPolicyReq(BaseModel):
    store_id:        str = "store_1"
    retention_days:  int = 30
    dry_run:         bool = True   # if True, only simulate — don't actually delete


# ── Occupancy Tracking ────────────────────────────────────────────────────────

@router.post("/occupancy/log")
def log_occupancy(req: OccupancyLogReq, db: Session = Depends(get_db)):
    max_cap  = req.max_capacity or ZONE_CAPACITY.get(req.zone, 50)
    breached = req.count > max_cap
    ev = OccupancyEvent(
        store_id=req.store_id,
        zone=req.zone,
        count=req.count,
        max_capacity=max_cap,
        breached=breached,
    )
    db.add(ev)

    if breached:
        db.add(AlertLog(
            job_id="occupancy",
            severity="CRITICAL",
            message=f"Occupancy limit breached in {req.zone}: {req.count}/{max_cap} people",
            timestamp_sec=0,
        ))

    db.commit()
    db.refresh(ev)
    return {
        "status":    "logged",
        "id":        ev.id,
        "breached":  breached,
        "count":     req.count,
        "max":       max_cap,
        "pct":       round(req.count / max_cap * 100, 1),
    }


@router.get("/occupancy")
def occupancy_status(store_id: str = "store_1", db: Session = Depends(get_db)):
    """Current occupancy per zone + breach history."""
    # Latest reading per zone
    all_events = (
        db.query(OccupancyEvent)
        .filter(OccupancyEvent.store_id == store_id)
        .order_by(OccupancyEvent.wall_time.desc())
        .all()
    )

    latest_per_zone: dict[str, OccupancyEvent] = {}
    for ev in all_events:
        if ev.zone not in latest_per_zone:
            latest_per_zone[ev.zone] = ev

    # Derive from job data if no manual logs
    if not latest_per_zone:
        jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()
        for j in jobs:
            r = j.result or {}
            pc = r.get("peak_crowd", {})
            if isinstance(pc, dict) and pc.get("count", 0) > 0:
                zone = "store"
                if zone not in latest_per_zone:
                    max_cap = ZONE_CAPACITY.get(zone, 150)
                    count   = pc.get("count", 0)
                    latest_per_zone[zone] = type("OE", (), {
                        "zone": zone, "count": count, "max_capacity": max_cap,
                        "breached": count > max_cap,
                        "wall_time": j.completed_at,
                    })()

    zones = []
    for zone, ev in latest_per_zone.items():
        max_cap = ev.max_capacity or ZONE_CAPACITY.get(zone, 50)
        pct     = round(ev.count / max_cap * 100, 1) if max_cap > 0 else 0
        zones.append({
            "zone":         zone,
            "current":      ev.count,
            "max_capacity": max_cap,
            "pct":          pct,
            "status":       "BREACHED" if ev.breached else "WARNING" if pct > 80 else "OK",
            "last_updated": str(ev.wall_time)[:16] if ev.wall_time else "unknown",
        })

    # Breach history (last 7 days)
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    breach_count = (
        db.query(OccupancyEvent)
        .filter(OccupancyEvent.store_id == store_id, OccupancyEvent.breached == True, OccupancyEvent.wall_time >= cutoff)
        .count()
    )

    return {
        "zones":          zones,
        "total_breaches_7d": breach_count,
        "any_breached":   any(z["status"] == "BREACHED" for z in zones),
        "zone_capacities": ZONE_CAPACITY,
    }


# ── Aisle / Fire Exit Blockage ────────────────────────────────────────────────

@router.post("/aisle-blockage/flag")
def flag_blockage(req: BlockageFlagReq, db: Session = Depends(get_db)):
    flag = {
        "id":          len(_blockage_flags) + 1,
        "zone":        req.zone,
        "location":    req.location,
        "blocked_by":  req.blocked_by,
        "severity":    req.severity,
        "description": req.description,
        "status":      "OPEN",
        "reported_at": datetime.datetime.utcnow().isoformat(),
        "resolved_at": None,
    }
    _blockage_flags.append(flag)

    db.add(AlertLog(
        job_id="compliance",
        severity=req.severity,
        message=f"Aisle/Exit blockage: {req.location} in {req.zone} — blocked by {req.blocked_by}",
        timestamp_sec=0,
    ))
    db.commit()
    return {"status": "flagged", "id": flag["id"]}


@router.get("/aisle-blockage")
def aisle_blockage_status():
    open_flags     = [f for f in _blockage_flags if f["status"] == "OPEN"]
    critical_flags = [f for f in open_flags if f["severity"] == "CRITICAL"]
    return {
        "open_flags":     open_flags,
        "total_open":     len(open_flags),
        "critical":       len(critical_flags),
        "all_flags":      list(reversed(_blockage_flags[-30:])),
        "status":         "CRITICAL" if critical_flags else "WARNING" if open_flags else "CLEAR",
        "safety_note":    "Fire exits and emergency aisles must remain clear at all times per safety regulations.",
    }


@router.post("/aisle-blockage/{flag_id}/resolve")
def resolve_blockage(flag_id: int):
    for f in _blockage_flags:
        if f["id"] == flag_id:
            f["status"]      = "RESOLVED"
            f["resolved_at"] = datetime.datetime.utcnow().isoformat()
            return {"status": "resolved", "id": flag_id}
    return {"status": "not_found"}


# ── CCTV Retention Policy ─────────────────────────────────────────────────────

@router.get("/cctv-retention")
def cctv_retention_status(db: Session = Depends(get_db)):
    """
    Show which jobs/footage are beyond retention policy and eligible for deletion.
    """
    jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=DEFAULT_RETENTION_DAYS)

    eligible_for_deletion = []
    within_retention      = []

    for j in jobs:
        if j.completed_at and j.completed_at < cutoff:
            age_days = (datetime.datetime.utcnow() - j.completed_at).days
            eligible_for_deletion.append({
                "job_id":    j.job_id,
                "filename":  j.filename,
                "age_days":  age_days,
                "completed": str(j.completed_at)[:10],
            })
        else:
            within_retention.append({
                "job_id":    j.job_id,
                "filename":  j.filename,
                "completed": str(j.completed_at)[:10] if j.completed_at else "unknown",
            })

    return {
        "retention_policy_days":  DEFAULT_RETENTION_DAYS,
        "total_jobs":             len(jobs),
        "eligible_for_deletion":  eligible_for_deletion,
        "within_retention":       within_retention,
        "deletion_count":         len(eligible_for_deletion),
        "compliance_status":      "ACTION_REQUIRED" if eligible_for_deletion else "COMPLIANT",
        "gdpr_note":              "Auto-deletion helps comply with GDPR/PDPA data minimization principles. Always verify local regulations before deleting.",
    }


@router.post("/cctv-retention/run")
def run_retention_policy(req: RetentionPolicyReq, db: Session = Depends(get_db)):
    """
    Simulate (or execute) auto-deletion of jobs beyond retention window.
    dry_run=True (default) only reports what would be deleted.
    """
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=req.retention_days)
    jobs   = db.query(AnalyticsJob).filter(
        AnalyticsJob.status == JobStatus.COMPLETED,
        AnalyticsJob.completed_at < cutoff,
    ).all()

    deleted = []
    for j in jobs:
        deleted.append({"job_id": j.job_id, "filename": j.filename, "completed": str(j.completed_at)[:10]})
        if not req.dry_run:
            # In production: also delete output files from disk
            db.delete(j)

    if not req.dry_run:
        db.commit()

    return {
        "dry_run":          req.dry_run,
        "retention_days":   req.retention_days,
        "records_affected": len(deleted),
        "deleted":          deleted,
        "message": (
            f"DRY RUN: {len(deleted)} records would be deleted" if req.dry_run else
            f"EXECUTED: {len(deleted)} records deleted from database"
        ),
        "warning": "This action is irreversible when dry_run=false. Ensure compliance with local data laws.",
    }


# ── Compliance Summary ────────────────────────────────────────────────────────

@router.get("/summary")
def compliance_summary(store_id: str = "store_1", db: Session = Depends(get_db)):
    breach_count = db.query(OccupancyEvent).filter(
        OccupancyEvent.store_id == store_id,
        OccupancyEvent.breached == True,
    ).count()

    open_blockages = len([f for f in _blockage_flags if f["status"] == "OPEN"])

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=DEFAULT_RETENTION_DAYS)
    overdue_footage = db.query(AnalyticsJob).filter(
        AnalyticsJob.status == JobStatus.COMPLETED,
        AnalyticsJob.completed_at < cutoff,
    ).count()

    score = 100
    if breach_count > 0:   score -= 20
    if open_blockages > 0: score -= 20
    if overdue_footage > 0: score -= 15

    return {
        "compliance_score":    max(0, score),
        "occupancy_breaches":  breach_count,
        "open_blockages":      open_blockages,
        "overdue_footage":     overdue_footage,
        "status":              "COMPLIANT" if score >= 90 else "NEEDS_ATTENTION" if score >= 70 else "NON_COMPLIANT",
    }
