"""
routers/inventory.py — Inventory & Shelf Management for Retail AI

POST /inventory/shelf-event        → log shelf empty/restocked event
GET  /inventory/shelf-events       → list shelf events
GET  /inventory/oos-duration       → out-of-stock duration per zone
GET  /inventory/fast-slow-shelves  → fast vs slow moving shelf analysis
GET  /inventory/restock-alerts     → current unresolved restock alerts
POST /inventory/restock/{event_id} → mark shelf as restocked
GET  /inventory/planogram          → planogram compliance check (rule-based)
GET  /inventory/lost-sales         → estimated lost sales from OOS duration
"""
import datetime
import random
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import AnalyticsJob, JobStatus, AlertLog, ShelfEvent

router = APIRouter(prefix="/inventory", tags=["inventory"])

# Average sale value per minute of OOS (configurable)
AVG_SALE_PER_MIN = 8.5   # ₹ per minute shelf is empty


class ShelfEventReq(BaseModel):
    store_id:      str = "store_1"
    job_id:        Optional[str] = None
    zone:          str
    event_type:    str   # EMPTY | LOW_STOCK | RESTOCKED
    timestamp_sec: Optional[float] = None
    duration_min:  Optional[float] = None


# ── Log Shelf Event ───────────────────────────────────────────────────────────

@router.post("/shelf-event")
def log_shelf_event(req: ShelfEventReq, db: Session = Depends(get_db)):
    ev = ShelfEvent(
        store_id=req.store_id,
        job_id=req.job_id,
        zone=req.zone,
        event_type=req.event_type,
        timestamp_sec=req.timestamp_sec,
        duration_min=req.duration_min,
    )
    db.add(ev)

    # If RESTOCKED, resolve the latest EMPTY event for this zone
    if req.event_type == "RESTOCKED":
        latest_empty = (
            db.query(ShelfEvent)
            .filter(
                ShelfEvent.store_id == req.store_id,
                ShelfEvent.zone == req.zone,
                ShelfEvent.event_type == "EMPTY",
                ShelfEvent.resolved_at == None,
            )
            .order_by(ShelfEvent.wall_time.desc())
            .first()
        )
        if latest_empty:
            latest_empty.resolved_at = datetime.datetime.utcnow()
            duration = (datetime.datetime.utcnow() - latest_empty.wall_time).total_seconds() / 60
            latest_empty.duration_min = round(duration, 1)
            ev.duration_min = round(duration, 1)

    db.commit()
    db.refresh(ev)
    return {"status": "logged", "id": ev.id, "event_type": ev.event_type, "zone": ev.zone}


# ── List Shelf Events ─────────────────────────────────────────────────────────

@router.get("/shelf-events")
def list_shelf_events(store_id: str = "store_1", limit: int = 50, db: Session = Depends(get_db)):
    events = (
        db.query(ShelfEvent)
        .filter(ShelfEvent.store_id == store_id)
        .order_by(ShelfEvent.wall_time.desc())
        .limit(limit)
        .all()
    )
    return {
        "total": len(events),
        "events": [
            {
                "id":           e.id,
                "zone":         e.zone,
                "event_type":   e.event_type,
                "duration_min": e.duration_min,
                "wall_time":    str(e.wall_time),
                "resolved_at":  str(e.resolved_at) if e.resolved_at else None,
                "resolved":     e.resolved_at is not None,
            }
            for e in events
        ],
    }


# ── Restock Alerts (unresolved EMPTY events) ──────────────────────────────────

@router.get("/restock-alerts")
def restock_alerts(store_id: str = "store_1", db: Session = Depends(get_db)):
    """All unresolved shelf-empty events = active restock needed."""
    unresolved = (
        db.query(ShelfEvent)
        .filter(
            ShelfEvent.store_id == store_id,
            ShelfEvent.event_type.in_(["EMPTY", "LOW_STOCK"]),
            ShelfEvent.resolved_at == None,
        )
        .order_by(ShelfEvent.wall_time.desc())
        .all()
    )

    alerts = []
    for e in unresolved:
        age_min = round((datetime.datetime.utcnow() - e.wall_time).total_seconds() / 60, 1)
        lost    = round(age_min * AVG_SALE_PER_MIN, 2)
        alerts.append({
            "id":           e.id,
            "zone":         e.zone,
            "event_type":   e.event_type,
            "age_minutes":  age_min,
            "estimated_lost_sales": lost,
            "urgency":      "CRITICAL" if age_min > 30 else "HIGH" if age_min > 10 else "MEDIUM",
            "wall_time":    str(e.wall_time),
        })

    # Also pull from AlertLog (from video processing)
    db_alerts = (
        db.query(AlertLog)
        .filter(AlertLog.severity == "CRITICAL", AlertLog.message.contains("SHELF"))
        .order_by(AlertLog.wall_time.desc())
        .limit(10)
        .all()
    )
    for a in db_alerts:
        alerts.append({
            "id":           f"log_{a.id}",
            "zone":         "Unknown",
            "event_type":   "EMPTY",
            "age_minutes":  round((datetime.datetime.utcnow() - a.wall_time).total_seconds() / 60, 1),
            "estimated_lost_sales": 0,
            "urgency":      "CRITICAL",
            "wall_time":    str(a.wall_time),
            "message":      a.message,
        })

    return {
        "total_alerts": len(alerts),
        "alerts":       alerts,
        "total_estimated_lost": round(sum(a.get("estimated_lost_sales", 0) for a in alerts), 2),
    }


# ── Mark Restocked ────────────────────────────────────────────────────────────

@router.post("/restock/{event_id}")
def mark_restocked(event_id: int, db: Session = Depends(get_db)):
    ev = db.query(ShelfEvent).filter(ShelfEvent.id == event_id).first()
    if not ev:
        raise HTTPException(404, "Shelf event not found")
    ev.resolved_at = datetime.datetime.utcnow()
    if ev.wall_time:
        ev.duration_min = round((ev.resolved_at - ev.wall_time).total_seconds() / 60, 1)
    db.commit()
    return {"status": "restocked", "duration_min": ev.duration_min}


# ── OOS Duration Tracking ─────────────────────────────────────────────────────

@router.get("/oos-duration")
def oos_duration(store_id: str = "store_1", db: Session = Depends(get_db)):
    """How long each zone was out-of-stock (resolved events only)."""
    resolved = (
        db.query(ShelfEvent)
        .filter(
            ShelfEvent.store_id == store_id,
            ShelfEvent.event_type == "EMPTY",
            ShelfEvent.resolved_at != None,
            ShelfEvent.duration_min != None,
        )
        .all()
    )

    zone_stats: dict[str, dict] = defaultdict(lambda: {"incidents": 0, "total_min": 0.0, "max_min": 0.0})
    for e in resolved:
        z = e.zone or "Unknown"
        zone_stats[z]["incidents"]  += 1
        zone_stats[z]["total_min"]  += e.duration_min
        zone_stats[z]["max_min"]     = max(zone_stats[z]["max_min"], e.duration_min)

    result = []
    for zone, s in sorted(zone_stats.items(), key=lambda x: -x[1]["total_min"]):
        avg_min = round(s["total_min"] / s["incidents"], 1) if s["incidents"] > 0 else 0
        lost    = round(s["total_min"] * AVG_SALE_PER_MIN, 2)
        result.append({
            "zone":              zone,
            "incidents":         s["incidents"],
            "total_oos_min":     round(s["total_min"], 1),
            "avg_oos_min":       avg_min,
            "max_oos_min":       round(s["max_min"], 1),
            "estimated_lost":    lost,
            "priority":          "HIGH" if s["total_min"] > 60 else "MEDIUM" if s["total_min"] > 20 else "LOW",
        })

    return {
        "zones":              result,
        "total_oos_min":      round(sum(s["total_min"] for s in zone_stats.values()), 1),
        "total_lost_sales":   round(sum(s["total_min"] * AVG_SALE_PER_MIN for s in zone_stats.values()), 2),
    }


# ── Fast vs Slow Moving Shelves ───────────────────────────────────────────────

@router.get("/fast-slow-shelves")
def fast_slow_shelves(store_id: str = "store_1", db: Session = Depends(get_db)):
    """
    Fast shelf = frequently goes EMPTY (high demand).
    Slow shelf = rarely visited (low demand).
    """
    events = db.query(ShelfEvent).filter(ShelfEvent.store_id == store_id).all()
    zone_empties: dict[str, int] = defaultdict(int)
    for e in events:
        if e.event_type == "EMPTY" and e.zone:
            zone_empties[e.zone] += 1

    # Also use zone footfall from jobs
    jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()
    zone_footfall: dict[str, int] = defaultdict(int)
    for j in jobs:
        zones = (j.result or {}).get("zones", {})
        for z, c in zones.get("unique_visitors", {}).items():
            zone_footfall[z] += c

    all_zones = set(list(zone_empties.keys()) + list(zone_footfall.keys()))
    result = []
    for zone in all_zones:
        empties  = zone_empties.get(zone, 0)
        footfall = zone_footfall.get(zone, 0)
        speed    = "FAST" if empties >= 3 else "MODERATE" if empties >= 1 else "SLOW"
        result.append({
            "zone":          zone,
            "empty_count":   empties,
            "footfall":      footfall,
            "speed":         speed,
            "recommendation": (
                "Increase stock quantity / reorder point" if speed == "FAST" else
                "Consider promotional push to increase sales" if speed == "SLOW" else
                "Monitor regularly"
            ),
        })

    result.sort(key=lambda x: -x["empty_count"])
    return {"shelves": result}


# ── Planogram Compliance ──────────────────────────────────────────────────────

@router.get("/planogram")
def planogram_compliance(db: Session = Depends(get_db)):
    """
    Rule-based planogram check using zone footfall vs expected layout.
    High-footfall zones should have high-margin products.
    """
    jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()
    zone_footfall: dict[str, int] = defaultdict(int)
    for j in jobs:
        zones = (j.result or {}).get("zones", {})
        for z, c in zones.get("unique_visitors", {}).items():
            zone_footfall[z] += c

    # Expected planogram rules
    PLANOGRAM_RULES = {
        "Entrance":    {"expected_product_type": "Promotional/Seasonal", "margin": "medium", "priority": "high"},
        "Electronics": {"expected_product_type": "High-margin electronics", "margin": "high",   "priority": "high"},
        "Grocery":     {"expected_product_type": "Daily essentials",       "margin": "low",    "priority": "medium"},
        "Checkout":    {"expected_product_type": "Impulse buy items",      "margin": "high",   "priority": "high"},
        "Apparel":     {"expected_product_type": "Seasonal fashion",       "margin": "high",   "priority": "medium"},
    }

    total_foot = sum(zone_footfall.values()) or 1
    result = []
    for zone, rules in PLANOGRAM_RULES.items():
        foot       = zone_footfall.get(zone, 0)
        foot_share = round(foot / total_foot * 100, 1)
        compliant  = not (foot_share > 25 and rules["margin"] == "low")
        result.append({
            "zone":                 zone,
            "footfall":             foot,
            "footfall_share":       foot_share,
            "expected_product":     rules["expected_product_type"],
            "expected_margin":      rules["margin"],
            "priority":             rules["priority"],
            "compliant":            compliant,
            "issue": (
                None if compliant else
                f"High-traffic zone ({foot_share}%) with low-margin products — consider repositioning high-margin items here"
            ),
        })

    compliant_count = sum(1 for r in result if r["compliant"])
    return {
        "zones":             result,
        "compliance_score":  round(compliant_count / len(result) * 100) if result else 100,
        "issues_found":      len(result) - compliant_count,
    }


# ── Lost Sales Estimate ───────────────────────────────────────────────────────

@router.get("/lost-sales")
def lost_sales_estimate(store_id: str = "store_1", db: Session = Depends(get_db)):
    """Estimate revenue lost due to OOS events."""
    resolved = (
        db.query(ShelfEvent)
        .filter(
            ShelfEvent.store_id == store_id,
            ShelfEvent.event_type == "EMPTY",
            ShelfEvent.duration_min != None,
        )
        .all()
    )
    unresolved = (
        db.query(ShelfEvent)
        .filter(
            ShelfEvent.store_id == store_id,
            ShelfEvent.event_type == "EMPTY",
            ShelfEvent.resolved_at == None,
        )
        .all()
    )

    resolved_lost   = sum((e.duration_min or 0) * AVG_SALE_PER_MIN for e in resolved)
    unresolved_lost = sum(
        (datetime.datetime.utcnow() - e.wall_time).total_seconds() / 60 * AVG_SALE_PER_MIN
        for e in unresolved
    )

    return {
        "resolved_incidents":    len(resolved),
        "unresolved_incidents":  len(unresolved),
        "resolved_lost_sales":   round(resolved_lost, 2),
        "unresolved_lost_sales": round(unresolved_lost, 2),
        "total_lost_sales":      round(resolved_lost + unresolved_lost, 2),
        "avg_per_minute":        AVG_SALE_PER_MIN,
        "currency":              "INR",
    }
