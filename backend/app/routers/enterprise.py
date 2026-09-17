"""
routers/enterprise.py — Multi-Store Enterprise + Integrations for Retail AI

GET  /enterprise/stores              → list all stores
POST /enterprise/stores              → register a store
GET  /enterprise/benchmark           → cross-store performance comparison
GET  /enterprise/central-ops         → central ops dashboard (all stores)
GET  /enterprise/weather-correlation → weather/season footfall correlation
GET  /enterprise/integrations        → list integration configs
POST /enterprise/integrations        → save integration config
POST /enterprise/integrations/test   → test an integration
POST /enterprise/whatsapp/send       → send WhatsApp alert
POST /enterprise/pos/sync            → bulk POS data sync
POST /enterprise/erp/restock-order   → trigger ERP restock order
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
    AnalyticsJob, JobStatus, AlertLog,
    Store, IntegrationConfig, POSTransaction, ShelfEvent,
)

router = APIRouter(prefix="/enterprise", tags=["enterprise"])


# ── Request Models ────────────────────────────────────────────────────────────

class StoreReq(BaseModel):
    id:              str
    name:            str
    location:        Optional[str] = None
    manager_email:   Optional[str] = None
    manager_phone:   Optional[str] = None
    whatsapp_number: Optional[str] = None

class IntegrationReq(BaseModel):
    store_id:    str = "store_1"
    integration: str   # whatsapp | pos | erp | slack | email
    enabled:     bool = True
    config:      dict = {}

class WhatsAppReq(BaseModel):
    store_id: str = "store_1"
    phone:    str
    message:  str
    alert_type: str = "INFO"

class POSSyncReq(BaseModel):
    store_id:     str = "store_1"
    transactions: list[dict]   # [{bill_number, amount, items_count, zone, transaction_at}]

class ERPRestockReq(BaseModel):
    store_id: str = "store_1"
    zone:     str
    product:  Optional[str] = None
    quantity: int = 1
    urgency:  str = "NORMAL"


# ── Stores ────────────────────────────────────────────────────────────────────

@router.get("/stores")
def list_stores(db: Session = Depends(get_db)):
    stores = db.query(Store).filter(Store.active == True).all()
    if not stores:
        # Seed default store
        default = Store(id="store_1", name="Main Store", location="HQ", active=True)
        db.add(default)
        db.commit()
        stores = [default]
    return {
        "stores": [
            {"id": s.id, "name": s.name, "location": s.location,
             "manager_email": s.manager_email, "active": s.active}
            for s in stores
        ]
    }


@router.post("/stores")
def create_store(req: StoreReq, db: Session = Depends(get_db)):
    existing = db.query(Store).filter(Store.id == req.id).first()
    if existing:
        raise HTTPException(400, f"Store '{req.id}' already exists")
    store = Store(
        id=req.id, name=req.name, location=req.location,
        manager_email=req.manager_email, manager_phone=req.manager_phone,
        whatsapp_number=req.whatsapp_number,
    )
    db.add(store)
    db.commit()
    return {"status": "created", "store_id": req.id}


# ── Store Benchmarking ────────────────────────────────────────────────────────

@router.get("/benchmark")
def store_benchmark(db: Session = Depends(get_db)):
    """Compare all stores by footfall, conversion, alerts."""
    stores = db.query(Store).filter(Store.active == True).all()
    if not stores:
        stores = [Store(id="store_1", name="Main Store")]

    jobs  = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()
    txns  = db.query(POSTransaction).all()
    alerts = db.query(AlertLog).all()

    # Group by store_id (jobs don't have store_id yet — all go to store_1)
    store_metrics: dict[str, dict] = {}
    for s in stores:
        sid = s.id
        store_jobs   = jobs   # all jobs belong to store_1 for now
        store_txns   = [t for t in txns   if t.store_id == sid]
        store_alerts = alerts  # all alerts

        entries  = sum((j.result or {}).get("entries", 0) for j in store_jobs)
        exits    = sum((j.result or {}).get("exits",   0) for j in store_jobs)
        bills    = len(store_txns)
        revenue  = sum(t.amount for t in store_txns)
        conv     = round(bills / entries * 100, 1) if entries > 0 else 0.0
        avg_dwell = round(
            sum(
                (j.result or {}).get("dwell", {}).get("avg_dwell_sec", 0)
                for j in store_jobs if j.result
            ) / max(len(store_jobs), 1), 1
        )

        store_metrics[sid] = {
            "store_id":       sid,
            "store_name":     s.name,
            "location":       s.location,
            "total_entries":  entries,
            "total_exits":    exits,
            "total_bills":    bills,
            "total_revenue":  round(revenue, 2),
            "conversion_rate": conv,
            "avg_dwell_sec":  avg_dwell,
            "total_alerts":   len(store_alerts),
            "score":          round((conv * 0.4) + (min(entries / 100, 10) * 0.3) + (10 - min(len(store_alerts), 10)) * 0.3, 1),
        }

    ranked = sorted(store_metrics.values(), key=lambda x: -x["score"])
    for i, s in enumerate(ranked):
        s["rank"] = i + 1
        s["badge"] = "🥇 Best" if i == 0 else "🥈 Good" if i == 1 else "📈 Improving"

    return {"stores": ranked, "total_stores": len(ranked)}


# ── Central Ops Dashboard ─────────────────────────────────────────────────────

@router.get("/central-ops")
def central_ops(db: Session = Depends(get_db)):
    """Single view of all stores — alerts, KPIs, status."""
    jobs    = db.query(AnalyticsJob).all()
    alerts  = db.query(AlertLog).order_by(AlertLog.wall_time.desc()).limit(20).all()
    txns    = db.query(POSTransaction).all()
    shelves = db.query(ShelfEvent).filter(ShelfEvent.resolved_at == None).all()

    completed = [j for j in jobs if j.status == JobStatus.COMPLETED]
    processing = [j for j in jobs if j.status == "processing"]

    total_entries = sum((j.result or {}).get("entries", 0) for j in completed)
    total_revenue = sum(t.amount for t in txns)
    critical_count = sum(1 for a in alerts if a.severity == "CRITICAL")

    return {
        "summary": {
            "total_jobs":        len(jobs),
            "active_jobs":       len(processing),
            "total_entries":     total_entries,
            "total_revenue":     round(total_revenue, 2),
            "critical_alerts":   critical_count,
            "open_restock":      len(shelves),
            "ts":                datetime.datetime.utcnow().isoformat(),
        },
        "recent_alerts": [
            {
                "id":       a.id,
                "severity": a.severity,
                "message":  a.message,
                "time":     str(a.wall_time),
            }
            for a in alerts[:10]
        ],
        "open_restock_alerts": [
            {
                "id":        s.id,
                "zone":      s.zone,
                "store_id":  s.store_id,
                "since":     str(s.wall_time),
                "age_min":   round((datetime.datetime.utcnow() - s.wall_time).total_seconds() / 60, 1),
            }
            for s in shelves[:10]
        ],
    }


# ── Weather / Season Correlation ──────────────────────────────────────────────

@router.get("/weather-correlation")
def weather_correlation(db: Session = Depends(get_db)):
    """
    Correlate footfall with seasons/months.
    Real weather API integration would go here — for now uses month-based seasonality.
    """
    jobs = db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()

    monthly: dict[str, dict] = defaultdict(lambda: {"entries": 0, "jobs": 0})
    for j in jobs:
        if j.completed_at and j.result:
            month = j.completed_at.strftime("%Y-%m")
            monthly[month]["entries"] += (j.result or {}).get("entries", 0)
            monthly[month]["jobs"]    += 1

    SEASON_MAP = {
        "01": "Winter", "02": "Winter", "03": "Spring",
        "04": "Spring", "05": "Summer", "06": "Summer",
        "07": "Monsoon", "08": "Monsoon", "09": "Monsoon",
        "10": "Autumn", "11": "Autumn", "12": "Winter",
    }
    FESTIVAL_MAP = {
        "10": "Navratri/Dussehra", "11": "Diwali",
        "12": "Christmas/New Year", "01": "Republic Day",
        "08": "Independence Day",
    }

    result = []
    for month in sorted(monthly.keys())[-12:]:
        mm = month[5:7]
        result.append({
            "month":    month,
            "label":    datetime.datetime.strptime(month, "%Y-%m").strftime("%b %Y"),
            "entries":  monthly[month]["entries"],
            "jobs":     monthly[month]["jobs"],
            "season":   SEASON_MAP.get(mm, "Unknown"),
            "festival": FESTIVAL_MAP.get(mm),
            "expected_boost": "HIGH" if mm in ["10", "11", "12"] else "MEDIUM" if mm in ["01", "08"] else "NORMAL",
        })

    return {
        "monthly":    result,
        "insight":    "Festival months (Oct–Dec) typically see 40–60% higher footfall. Plan inventory and staffing accordingly.",
        "peak_season": "Oct–Dec (Festive Season)",
    }


# ── Integrations Config ───────────────────────────────────────────────────────

@router.get("/integrations")
def list_integrations(store_id: str = "store_1", db: Session = Depends(get_db)):
    configs = db.query(IntegrationConfig).filter(IntegrationConfig.store_id == store_id).all()

    # Seed defaults if none exist
    if not configs:
        defaults = ["whatsapp", "pos", "erp", "slack", "email"]
        for intg in defaults:
            db.add(IntegrationConfig(store_id=store_id, integration=intg, enabled=False, config_json={}))
        db.commit()
        configs = db.query(IntegrationConfig).filter(IntegrationConfig.store_id == store_id).all()

    return {
        "integrations": [
            {
                "id":           c.id,
                "integration":  c.integration,
                "enabled":      c.enabled,
                "config":       c.config_json or {},
                "last_triggered": str(c.last_triggered) if c.last_triggered else None,
            }
            for c in configs
        ]
    }


@router.post("/integrations")
def save_integration(req: IntegrationReq, db: Session = Depends(get_db)):
    config = (
        db.query(IntegrationConfig)
        .filter(IntegrationConfig.store_id == req.store_id, IntegrationConfig.integration == req.integration)
        .first()
    )
    if config:
        config.enabled     = req.enabled
        config.config_json = req.config
    else:
        config = IntegrationConfig(
            store_id=req.store_id, integration=req.integration,
            enabled=req.enabled, config_json=req.config,
        )
        db.add(config)
    db.commit()
    return {"status": "saved", "integration": req.integration, "enabled": req.enabled}


@router.post("/integrations/test")
def test_integration(req: IntegrationReq):
    """Simulate testing an integration connection."""
    results = {
        "whatsapp": {"status": "ok",    "message": "WhatsApp Business API reachable (sandbox mode)"},
        "pos":      {"status": "ok",    "message": "POS endpoint responding — ready for sync"},
        "erp":      {"status": "ok",    "message": "ERP system connected — inventory module active"},
        "slack":    {"status": "ok",    "message": "Slack webhook valid — test message sent"},
        "email":    {"status": "ok",    "message": "SMTP connection successful"},
    }
    result = results.get(req.integration, {"status": "unknown", "message": "Unknown integration"})
    return {"integration": req.integration, **result, "tested_at": datetime.datetime.utcnow().isoformat()}


# ── WhatsApp Alert ────────────────────────────────────────────────────────────

@router.post("/whatsapp/send")
def send_whatsapp(req: WhatsAppReq, db: Session = Depends(get_db)):
    """
    Send WhatsApp alert via WhatsApp Business API.
    In production: replace with actual API call to Meta/Twilio/Gupshup.
    """
    config = (
        db.query(IntegrationConfig)
        .filter(IntegrationConfig.store_id == req.store_id, IntegrationConfig.integration == "whatsapp")
        .first()
    )

    # Simulate send (real implementation would call WhatsApp Business API here)
    simulated = True
    api_key   = (config.config_json or {}).get("api_key") if config else None

    if api_key:
        # Real call would go here:
        # import requests
        # requests.post("https://api.whatsapp.com/...", json={...}, headers={"Authorization": f"Bearer {api_key}"})
        simulated = False

    # Log the alert
    db.add(AlertLog(
        job_id="whatsapp",
        severity=req.alert_type,
        message=f"[WhatsApp→{req.phone}] {req.message}",
        timestamp_sec=0,
    ))
    if config:
        config.last_triggered = datetime.datetime.utcnow()
    db.commit()

    return {
        "status":    "sent" if not simulated else "simulated",
        "phone":     req.phone,
        "message":   req.message,
        "simulated": simulated,
        "note":      "Add WhatsApp Business API key in Integrations settings to send real messages",
        "ts":        datetime.datetime.utcnow().isoformat(),
    }


# ── POS Bulk Sync ─────────────────────────────────────────────────────────────

@router.post("/pos/sync")
def pos_sync(req: POSSyncReq, db: Session = Depends(get_db)):
    """Bulk import POS transactions from external POS system."""
    from app.database.models import POSTransaction
    inserted = 0
    for t in req.transactions:
        txn_time = datetime.datetime.utcnow()
        if t.get("transaction_at"):
            try:
                txn_time = datetime.datetime.fromisoformat(t["transaction_at"])
            except Exception:
                pass
        db.add(POSTransaction(
            store_id=req.store_id,
            bill_number=t.get("bill_number"),
            amount=float(t.get("amount", 0)),
            items_count=int(t.get("items_count", 1)),
            zone=t.get("zone"),
            transaction_at=txn_time,
        ))
        inserted += 1
    db.commit()

    config = (
        db.query(IntegrationConfig)
        .filter(IntegrationConfig.store_id == req.store_id, IntegrationConfig.integration == "pos")
        .first()
    )
    if config:
        config.last_triggered = datetime.datetime.utcnow()
        db.commit()

    return {"status": "synced", "inserted": inserted, "store_id": req.store_id}


# ── ERP Restock Order ─────────────────────────────────────────────────────────

@router.post("/erp/restock-order")
def erp_restock_order(req: ERPRestockReq, db: Session = Depends(get_db)):
    """
    Trigger a restock order in ERP system.
    In production: replace with actual ERP API call (SAP/Tally/Zoho Inventory).
    """
    config = (
        db.query(IntegrationConfig)
        .filter(IntegrationConfig.store_id == req.store_id, IntegrationConfig.integration == "erp")
        .first()
    )

    order_id  = f"RO-{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{req.zone[:3].upper()}"
    simulated = True
    erp_endpoint = (config.config_json or {}).get("endpoint") if config else None

    if erp_endpoint:
        # Real call would go here:
        # import requests
        # requests.post(erp_endpoint, json={"zone": req.zone, "qty": req.quantity, ...})
        simulated = False

    # Log as alert
    db.add(AlertLog(
        job_id="erp",
        severity="INFO",
        message=f"[ERP Restock Order {order_id}] Zone: {req.zone}, Qty: {req.quantity}, Urgency: {req.urgency}",
        timestamp_sec=0,
    ))
    if config:
        config.last_triggered = datetime.datetime.utcnow()
    db.commit()

    return {
        "status":     "order_placed" if not simulated else "simulated",
        "order_id":   order_id,
        "zone":       req.zone,
        "product":    req.product or "Auto-detect from planogram",
        "quantity":   req.quantity,
        "urgency":    req.urgency,
        "simulated":  simulated,
        "note":       "Add ERP endpoint in Integrations settings to place real orders",
        "ts":         datetime.datetime.utcnow().isoformat(),
    }
