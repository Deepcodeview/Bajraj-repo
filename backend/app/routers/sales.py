"""
routers/sales.py — Sales & Marketing Analytics for Retail AI

POST /sales/pos/transaction        → log a POS transaction
GET  /sales/pos/transactions       → list transactions
GET  /sales/conversion             → footfall-to-sales conversion rate
GET  /sales/peak-hours             → peak hour analysis from all jobs
GET  /sales/zone-interest          → zone visit vs sales gap analysis
POST /sales/promotions             → create a promotion record
GET  /sales/promotions             → list promotions with effectiveness
GET  /sales/promotions/{id}        → single promotion effectiveness
GET  /sales/repeat-visitors        → same-day re-entry pattern analysis
"""
import datetime
import random
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import (
    AnalyticsJob, JobStatus, CrossingEvent,
    POSTransaction, Promotion,
)

router = APIRouter(prefix="/sales", tags=["sales"])


# ── Request Models ────────────────────────────────────────────────────────────

class POSReq(BaseModel):
    store_id:    str = "store_1"
    bill_number: Optional[str] = None
    amount:      float = 0.0
    items_count: int = 1
    zone:        Optional[str] = None
    transaction_at: Optional[str] = None   # ISO string, defaults to now

class PromotionReq(BaseModel):
    store_id:     str = "store_1"
    name:         str
    zone:         Optional[str] = None
    discount_pct: float = 0.0
    start_date:   str   # ISO date string
    end_date:     str


# ── POS Transactions ──────────────────────────────────────────────────────────

@router.post("/pos/transaction")
def log_transaction(req: POSReq, db: Session = Depends(get_db)):
    txn_time = datetime.datetime.utcnow()
    if req.transaction_at:
        try:
            txn_time = datetime.datetime.fromisoformat(req.transaction_at)
        except Exception:
            pass

    txn = POSTransaction(
        store_id=req.store_id,
        bill_number=req.bill_number,
        amount=req.amount,
        items_count=req.items_count,
        zone=req.zone,
        transaction_at=txn_time,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return {"status": "logged", "id": txn.id, "amount": txn.amount}


@router.get("/pos/transactions")
def list_transactions(store_id: str = "store_1", limit: int = 50, db: Session = Depends(get_db)):
    txns = (
        db.query(POSTransaction)
        .filter(POSTransaction.store_id == store_id)
        .order_by(POSTransaction.transaction_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "total": len(txns),
        "transactions": [
            {
                "id":             t.id,
                "bill_number":    t.bill_number,
                "amount":         t.amount,
                "items_count":    t.items_count,
                "zone":           t.zone,
                "transaction_at": str(t.transaction_at),
            }
            for t in txns
        ],
    }


# ── Conversion Rate ───────────────────────────────────────────────────────────

@router.get("/conversion")
def conversion_rate(store_id: str = "store_1", db: Session = Depends(get_db)):
    """Footfall-to-sales conversion: (bills / entries) × 100"""
    jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()
    total_entries = sum((j.result or {}).get("entries", 0) for j in jobs)

    txns = db.query(POSTransaction).filter(POSTransaction.store_id == store_id).all()
    total_bills   = len(txns)
    total_revenue = sum(t.amount for t in txns)

    conversion = round((total_bills / total_entries * 100), 1) if total_entries > 0 else 0.0

    # Zone-wise breakdown
    zone_bills: dict[str, int] = defaultdict(int)
    zone_revenue: dict[str, float] = defaultdict(float)
    for t in txns:
        if t.zone:
            zone_bills[t.zone]   += 1
            zone_revenue[t.zone] += t.amount

    # Zone footfall from jobs
    zone_footfall: dict[str, int] = defaultdict(int)
    for j in jobs:
        zones = (j.result or {}).get("zones", {})
        for z, c in zones.get("unique_visitors", {}).items():
            zone_footfall[z] += c

    zone_conversion = {}
    for z in zone_footfall:
        bills = zone_bills.get(z, 0)
        foot  = zone_footfall[z]
        zone_conversion[z] = {
            "footfall":   foot,
            "bills":      bills,
            "conversion": round(bills / foot * 100, 1) if foot > 0 else 0.0,
            "revenue":    round(zone_revenue.get(z, 0), 2),
            "gap":        "HIGH" if foot > 50 and bills < 5 else "NORMAL",
        }

    return {
        "total_entries":    total_entries,
        "total_bills":      total_bills,
        "total_revenue":    round(total_revenue, 2),
        "conversion_rate":  conversion,
        "avg_bill_value":   round(total_revenue / total_bills, 2) if total_bills > 0 else 0.0,
        "zone_conversion":  zone_conversion,
        "insight": (
            f"Conversion rate is {conversion}%. "
            + ("Good performance." if conversion >= 20 else
               "Below 20% — consider improving product placement and staff engagement.")
        ),
    }


# ── Peak Hours Analysis ───────────────────────────────────────────────────────

@router.get("/peak-hours")
def peak_hours(db: Session = Depends(get_db)):
    """Aggregate crowd timeline from all completed jobs to find peak hours."""
    jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()

    # Bucket by hour-of-day (0–23) using wall_time of crossing events
    hour_entries: dict[int, int] = defaultdict(int)
    dow_entries:  dict[int, int] = defaultdict(int)   # 0=Mon

    for j in jobs:
        if not j.completed_at or not j.result:
            continue
        entries = (j.result or {}).get("entries", 0)
        hour = j.completed_at.hour
        dow  = j.completed_at.weekday()
        hour_entries[hour] += entries
        dow_entries[dow]   += entries

    # Fill all 24 hours
    hours_data = [
        {
            "hour":    h,
            "label":   f"{h:02d}:00",
            "entries": hour_entries.get(h, 0),
            "tier":    "peak" if hour_entries.get(h, 0) >= max(hour_entries.values(), default=1) * 0.7
                       else "moderate" if hour_entries.get(h, 0) >= max(hour_entries.values(), default=1) * 0.4
                       else "low",
        }
        for h in range(24)
    ]

    dow_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    dow_data = [
        {"day": dow_labels[d], "entries": dow_entries.get(d, 0)}
        for d in range(7)
    ]

    peak_hour = max(hour_entries, key=hour_entries.get) if hour_entries else 18
    peak_dow  = max(dow_entries,  key=dow_entries.get)  if dow_entries  else 5

    return {
        "hours":      hours_data,
        "dow":        dow_data,
        "peak_hour":  f"{peak_hour:02d}:00",
        "peak_day":   dow_labels[peak_dow],
        "staffing_recommendation": {
            "peak_hours":    f"{peak_hour:02d}:00–{(peak_hour+2)%24:02d}:00",
            "staff_needed":  "Maximum — all counters open",
            "off_peak":      "Reduce to 40% staff",
            "best_promo_time": f"30 min before peak ({(peak_hour-1)%24:02d}:30)",
        },
    }


# ── Zone Interest vs Sales Gap ────────────────────────────────────────────────

@router.get("/zone-interest")
def zone_interest(store_id: str = "store_1", db: Session = Depends(get_db)):
    """Zones with high footfall but low sales = display/pricing improvement needed."""
    jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()

    zone_footfall: dict[str, int]   = defaultdict(int)
    zone_dwell:    dict[str, list]  = defaultdict(list)

    for j in jobs:
        r = j.result or {}
        zones = r.get("zones", {})
        for z, c in zones.get("unique_visitors", {}).items():
            zone_footfall[z] += c

    txns = db.query(POSTransaction).filter(POSTransaction.store_id == store_id).all()
    zone_bills: dict[str, int] = defaultdict(int)
    for t in txns:
        if t.zone:
            zone_bills[t.zone] += 1

    total_foot = sum(zone_footfall.values()) or 1
    result = []
    for zone, foot in sorted(zone_footfall.items(), key=lambda x: -x[1]):
        bills = zone_bills.get(zone, 0)
        conv  = round(bills / foot * 100, 1) if foot > 0 else 0.0
        foot_share = round(foot / total_foot * 100, 1)
        gap_score  = foot_share - conv   # high = lots of visitors but few buyers

        result.append({
            "zone":        zone,
            "footfall":    foot,
            "foot_share":  foot_share,
            "bills":       bills,
            "conversion":  conv,
            "gap_score":   round(gap_score, 1),
            "action": (
                "🔴 High priority: Improve display, pricing, or staff assistance"
                if gap_score > 20 else
                "🟡 Monitor: Moderate gap — consider promotional signage"
                if gap_score > 10 else
                "✅ Healthy conversion"
            ),
        })

    return {"zones": result, "total_footfall": sum(zone_footfall.values())}


# ── Promotions ────────────────────────────────────────────────────────────────

@router.post("/promotions")
def create_promotion(req: PromotionReq, db: Session = Depends(get_db)):
    try:
        start = datetime.datetime.fromisoformat(req.start_date)
        end   = datetime.datetime.fromisoformat(req.end_date)
    except Exception:
        raise HTTPException(400, "Invalid date format. Use ISO format: 2024-01-15")

    # Auto-fill pre/post footfall from jobs in date range
    jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()
    pre_foot = post_foot = 0
    for j in jobs:
        if not j.completed_at or not j.result:
            continue
        entries = (j.result or {}).get("entries", 0)
        if j.completed_at < start:
            pre_foot  += entries
        elif start <= j.completed_at <= end:
            post_foot += entries

    promo = Promotion(
        store_id=req.store_id,
        name=req.name,
        zone=req.zone,
        discount_pct=req.discount_pct,
        start_date=start,
        end_date=end,
        pre_footfall=pre_foot,
        post_footfall=post_foot,
    )
    db.add(promo)
    db.commit()
    db.refresh(promo)
    return {"status": "created", "id": promo.id, "pre_footfall": pre_foot, "post_footfall": post_foot}


@router.get("/promotions")
def list_promotions(store_id: str = "store_1", db: Session = Depends(get_db)):
    promos = db.query(Promotion).filter(Promotion.store_id == store_id).order_by(Promotion.start_date.desc()).all()
    result = []
    for p in promos:
        lift = 0.0
        if p.pre_footfall and p.pre_footfall > 0:
            lift = round((p.post_footfall - p.pre_footfall) / p.pre_footfall * 100, 1)
        now = datetime.datetime.utcnow()
        status = "active" if p.start_date <= now <= p.end_date else ("upcoming" if now < p.start_date else "ended")
        result.append({
            "id":           p.id,
            "name":         p.name,
            "zone":         p.zone,
            "discount_pct": p.discount_pct,
            "start_date":   str(p.start_date)[:10],
            "end_date":     str(p.end_date)[:10],
            "status":       status,
            "pre_footfall":  p.pre_footfall or 0,
            "post_footfall": p.post_footfall or 0,
            "footfall_lift": lift,
            "effective":    lift > 5,
        })
    return {"promotions": result, "total": len(result)}


# ── Repeat Visitor Detection ──────────────────────────────────────────────────

@router.get("/repeat-visitors")
def repeat_visitors(db: Session = Depends(get_db)):
    """
    Detect same-day re-entry patterns from crossing events.
    A person who has both entry + exit + entry again on same job = repeat visitor.
    """
    jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()

    repeat_count = 0
    total_visitors = 0
    repeat_by_job = []

    for j in jobs:
        events = (
            db.query(CrossingEvent)
            .filter(CrossingEvent.job_id == j.job_id)
            .order_by(CrossingEvent.timestamp_sec)
            .all()
        )
        # Count persons with >1 entry event
        person_entries: dict[int, int] = defaultdict(int)
        for e in events:
            if e.event_type == "entry":
                person_entries[e.global_id] += 1

        repeats = sum(1 for c in person_entries.values() if c > 1)
        total   = len(person_entries)
        repeat_count   += repeats
        total_visitors += total

        if total > 0:
            repeat_by_job.append({
                "job_id":        j.job_id,
                "filename":      j.filename,
                "total_visitors": total,
                "repeat_visitors": repeats,
                "repeat_rate":   round(repeats / total * 100, 1),
            })

    repeat_rate = round(repeat_count / total_visitors * 100, 1) if total_visitors > 0 else 0.0

    return {
        "total_visitors":   total_visitors,
        "repeat_visitors":  repeat_count,
        "repeat_rate":      repeat_rate,
        "by_job":           repeat_by_job,
        "insight": (
            f"{repeat_rate}% repeat visit rate. "
            + ("Strong loyalty signal — consider loyalty program." if repeat_rate > 15 else
               "Low repeat rate — focus on retention strategies.")
        ),
    }
