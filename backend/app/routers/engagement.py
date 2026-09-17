"""
routers/engagement.py — Customer Engagement for Retail AI

POST /engagement/signage/trigger    → trigger digital signage offer for a zone
GET  /engagement/signage/active     → list active signage triggers
POST /engagement/feedback           → submit feedback kiosk entry
GET  /engagement/feedback/analysis  → correlate feedback with zone dwell data
POST /engagement/offers/register    → register loyalty customer opt-in
GET  /engagement/offers             → list personalized offers
POST /engagement/offers/trigger     → trigger push notification for customer
GET  /engagement/summary            → engagement summary
"""
import datetime
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import AnalyticsJob, JobStatus, FeedbackEntry

router = APIRouter(prefix="/engagement", tags=["engagement"])

# In-memory stores
_signage_triggers: list[dict] = []
_loyalty_customers: list[dict] = []
_offer_notifications: list[dict] = []

# Zone → offer mapping (configurable)
ZONE_OFFERS = {
    "Electronics": "🔌 10% off on accessories today!",
    "Apparel":     "👗 Buy 2 Get 1 Free on selected items",
    "Grocery":     "🛒 Fresh arrivals — check today's deals",
    "Entrance":    "🎉 Welcome! Today's top deals inside →",
    "Checkout":    "💳 Add ₹200 more for free delivery",
}


class SignageTriggerReq(BaseModel):
    zone:        str
    screen_id:   Optional[str] = None
    offer_text:  Optional[str] = None   # override default zone offer
    duration_sec: int = 30
    triggered_by: str = "dwell_detection"  # dwell_detection | manual | schedule


class FeedbackReq(BaseModel):
    store_id:    str = "store_1"
    zone:        Optional[str] = None   # last zone visited before exit
    rating:      int                    # 1–5
    comment:     Optional[str] = None
    customer_id: Optional[str] = None  # loyalty ID if opt-in


class LoyaltyCustomerReq(BaseModel):
    customer_id:  str
    name:         Optional[str] = None
    phone:        Optional[str] = None
    preferences:  Optional[list] = None   # ["Electronics", "Apparel"]
    opt_in:       bool = True


class OfferTriggerReq(BaseModel):
    customer_id: str
    zone:        str
    offer_text:  Optional[str] = None


# ── Digital Signage ───────────────────────────────────────────────────────────

@router.post("/signage/trigger")
def trigger_signage(req: SignageTriggerReq):
    offer = req.offer_text or ZONE_OFFERS.get(req.zone, f"Special offer in {req.zone}!")
    trigger = {
        "id":           len(_signage_triggers) + 1,
        "zone":         req.zone,
        "screen_id":    req.screen_id or f"screen_{req.zone.lower()}",
        "offer_text":   offer,
        "duration_sec": req.duration_sec,
        "triggered_by": req.triggered_by,
        "active":       True,
        "triggered_at": datetime.datetime.utcnow().isoformat(),
        "expires_at":   (datetime.datetime.utcnow() + datetime.timedelta(seconds=req.duration_sec)).isoformat(),
    }
    _signage_triggers.append(trigger)
    return {"status": "triggered", "id": trigger["id"], "offer": offer, "screen": trigger["screen_id"]}


@router.get("/signage/active")
def active_signage():
    now    = datetime.datetime.utcnow()
    active = [
        t for t in _signage_triggers
        if t["active"] and datetime.datetime.fromisoformat(t["expires_at"]) > now
    ]
    # Mark expired
    for t in _signage_triggers:
        if t["active"] and datetime.datetime.fromisoformat(t["expires_at"]) <= now:
            t["active"] = False

    return {
        "active":       active,
        "total_active": len(active),
        "zone_offers":  ZONE_OFFERS,
        "recent":       list(reversed(_signage_triggers[-10:])),
    }


# ── Feedback Kiosk ────────────────────────────────────────────────────────────

@router.post("/feedback")
def submit_feedback(req: FeedbackReq, db: Session = Depends(get_db)):
    if not 1 <= req.rating <= 5:
        return {"error": "Rating must be between 1 and 5"}
    entry = FeedbackEntry(
        store_id=req.store_id,
        zone=req.zone,
        rating=req.rating,
        comment=req.comment,
        customer_id=req.customer_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {"status": "submitted", "id": entry.id, "rating": req.rating}


@router.get("/feedback/analysis")
def feedback_analysis(store_id: str = "store_1", db: Session = Depends(get_db)):
    """
    Correlate feedback ratings with zone dwell data.
    Low rating + high dwell = frustration zone.
    Low rating + low dwell = avoidance zone.
    """
    entries = db.query(FeedbackEntry).filter(FeedbackEntry.store_id == store_id).all()

    if not entries:
        return {"total": 0, "avg_rating": None, "zones": [], "insight": "No feedback data yet"}

    # Per-zone stats
    zone_ratings: dict[str, list] = defaultdict(list)
    for e in entries:
        zone = e.zone or "General"
        zone_ratings[zone].append(e.rating)

    # Zone dwell from jobs
    jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()
    zone_dwell: dict[str, list] = defaultdict(list)
    for j in jobs:
        dwell = (j.result or {}).get("dwell", {})
        zone_d = dwell.get("by_zone", {})
        for z, d_sec in zone_d.items():
            if isinstance(d_sec, (int, float)):
                zone_dwell[z].append(d_sec)

    all_zones = set(list(zone_ratings.keys()) + list(zone_dwell.keys()))
    zone_analysis = []
    for zone in all_zones:
        ratings  = zone_ratings.get(zone, [])
        dwells   = zone_dwell.get(zone, [])
        avg_r    = round(sum(ratings) / len(ratings), 2) if ratings else None
        avg_d    = round(sum(dwells) / len(dwells) / 60, 1) if dwells else None  # minutes

        if avg_r is not None and avg_d is not None:
            pattern = (
                "FRUSTRATION" if avg_r < 3 and avg_d > 3 else
                "AVOIDANCE"   if avg_r < 3 and (avg_d is None or avg_d < 1) else
                "ENGAGED"     if avg_r >= 4 and avg_d > 2 else
                "NEUTRAL"
            )
        else:
            pattern = "INSUFFICIENT_DATA"

        zone_analysis.append({
            "zone":          zone,
            "avg_rating":    avg_r,
            "avg_dwell_min": avg_d,
            "feedback_count": len(ratings),
            "pattern":       pattern,
            "recommendation": (
                "Investigate pain points — customers spend time but leave unhappy" if pattern == "FRUSTRATION" else
                "Zone is being avoided — check product relevance and layout" if pattern == "AVOIDANCE" else
                "High engagement and satisfaction — maintain current setup" if pattern == "ENGAGED" else
                "Collect more feedback for actionable insights"
            ),
        })

    zone_analysis.sort(key=lambda x: (x["avg_rating"] or 5))

    all_ratings = [e.rating for e in entries]
    avg_overall = round(sum(all_ratings) / len(all_ratings), 2)

    return {
        "total":       len(entries),
        "avg_rating":  avg_overall,
        "zones":       zone_analysis,
        "low_rated":   [z for z in zone_analysis if z["avg_rating"] and z["avg_rating"] < 3],
        "insight":     f"Overall store rating: {avg_overall}/5. Focus on: {', '.join(z['zone'] for z in zone_analysis[:2] if z['avg_rating'] and z['avg_rating'] < 3) or 'No critical zones'}",
    }


# ── Personalized Offers ───────────────────────────────────────────────────────

@router.post("/offers/register")
def register_loyalty_customer(req: LoyaltyCustomerReq):
    existing = next((c for c in _loyalty_customers if c["customer_id"] == req.customer_id), None)
    if existing:
        existing.update({"opt_in": req.opt_in, "preferences": req.preferences or existing.get("preferences", [])})
        return {"status": "updated", "customer_id": req.customer_id}

    customer = {
        "customer_id":  req.customer_id,
        "name":         req.name or "Customer",
        "phone":        req.phone,
        "preferences":  req.preferences or [],
        "opt_in":       req.opt_in,
        "registered_at": datetime.datetime.utcnow().isoformat(),
        "visit_count":  0,
    }
    _loyalty_customers.append(customer)
    return {"status": "registered", "customer_id": req.customer_id}


@router.get("/offers")
def list_offers():
    opted_in = [c for c in _loyalty_customers if c.get("opt_in")]
    return {
        "total_loyalty_customers": len(_loyalty_customers),
        "opted_in":                len(opted_in),
        "zone_offers":             ZONE_OFFERS,
        "recent_notifications":    list(reversed(_offer_notifications[-10:])),
        "customers":               opted_in[:20],
    }


@router.post("/offers/trigger")
def trigger_offer(req: OfferTriggerReq):
    """Send personalized push notification to loyalty customer in zone."""
    customer = next((c for c in _loyalty_customers if c["customer_id"] == req.customer_id), None)
    if not customer:
        return {"error": "Customer not found or not registered"}
    if not customer.get("opt_in"):
        return {"error": "Customer has not opted in to notifications"}

    offer = req.offer_text or ZONE_OFFERS.get(req.zone, f"Special offer in {req.zone}!")

    # In production: send via FCM/SMS/WhatsApp
    notification = {
        "id":           len(_offer_notifications) + 1,
        "customer_id":  req.customer_id,
        "customer_name": customer.get("name"),
        "zone":         req.zone,
        "offer":        offer,
        "channel":      "push_notification",  # FCM in production
        "status":       "sent_simulated",
        "sent_at":      datetime.datetime.utcnow().isoformat(),
    }
    _offer_notifications.append(notification)
    customer["visit_count"] = customer.get("visit_count", 0) + 1

    return {
        "status":   "sent",
        "id":       notification["id"],
        "customer": req.customer_id,
        "offer":    offer,
        "note":     "Simulated — connect FCM/SMS API in production",
    }


# ── Engagement Summary ────────────────────────────────────────────────────────

@router.get("/summary")
def engagement_summary(store_id: str = "store_1", db: Session = Depends(get_db)):
    total_feedback   = db.query(FeedbackEntry).filter(FeedbackEntry.store_id == store_id).count()
    entries          = db.query(FeedbackEntry).filter(FeedbackEntry.store_id == store_id).all()
    avg_rating       = round(sum(e.rating for e in entries) / len(entries), 2) if entries else None
    active_signage   = sum(
        1 for t in _signage_triggers
        if t["active"] and datetime.datetime.fromisoformat(t["expires_at"]) > datetime.datetime.utcnow()
    )
    return {
        "total_feedback":       total_feedback,
        "avg_rating":           avg_rating,
        "loyalty_customers":    len(_loyalty_customers),
        "opted_in":             sum(1 for c in _loyalty_customers if c.get("opt_in")),
        "active_signage":       active_signage,
        "total_notifications":  len(_offer_notifications),
    }
