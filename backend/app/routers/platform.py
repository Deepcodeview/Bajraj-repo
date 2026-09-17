"""
routers/platform.py — Platform / Ecosystem: Whitelabel, API Keys, Language, Role Dashboards

GET  /platform/whitelabel              → get whitelabel config
POST /platform/whitelabel              → save whitelabel config
GET  /platform/api-keys                → list API keys
POST /platform/api-keys                → generate new API key
DELETE /platform/api-keys/{id}         → revoke API key
POST /platform/api-keys/{id}/test      → test API key (simulate 3rd party call)
GET  /platform/languages               → list supported languages + translations
POST /platform/language/set            → set active language for store
GET  /platform/role-dashboards         → get role dashboard widget config
POST /platform/role-dashboards         → save role dashboard config
GET  /platform/saas/clients            → list whitelabel clients (admin only)
"""
import datetime
import hashlib
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import WhitelabelConfig, APIKey

router = APIRouter(prefix="/platform", tags=["platform"])

# ── Supported Languages ───────────────────────────────────────────────────────

SUPPORTED_LANGUAGES = {
    "en": {"name": "English",  "native": "English",  "flag": "🇬🇧"},
    "hi": {"name": "Hindi",    "native": "हिंदी",     "flag": "🇮🇳"},
    "mr": {"name": "Marathi",  "native": "मराठी",     "flag": "🇮🇳"},
    "ta": {"name": "Tamil",    "native": "தமிழ்",     "flag": "🇮🇳"},
    "te": {"name": "Telugu",   "native": "తెలుగు",    "flag": "🇮🇳"},
}

# ── Role Dashboard Widget Configs ─────────────────────────────────────────────

DEFAULT_ROLE_WIDGETS = {
    "store_manager": [
        {"id": "footfall_kpi",    "label": "Footfall KPIs",       "enabled": True,  "order": 1},
        {"id": "zone_heatmap",    "label": "Zone Heatmap",         "enabled": True,  "order": 2},
        {"id": "restock_alerts",  "label": "Restock Alerts",       "enabled": True,  "order": 3},
        {"id": "billing_gap",     "label": "Billing Gap",          "enabled": True,  "order": 4},
        {"id": "shift_summary",   "label": "Shift Summary",        "enabled": True,  "order": 5},
        {"id": "ai_forecast",     "label": "AI Forecast",          "enabled": True,  "order": 6},
        {"id": "staff_load",      "label": "Staff Load",           "enabled": True,  "order": 7},
        {"id": "compliance_score","label": "Compliance Score",     "enabled": False, "order": 8},
    ],
    "analyst": [
        {"id": "footfall_kpi",    "label": "Footfall KPIs",        "enabled": True,  "order": 1},
        {"id": "zone_heatmap",    "label": "Zone Heatmap",         "enabled": True,  "order": 2},
        {"id": "trends_chart",    "label": "Trends Chart",         "enabled": True,  "order": 3},
        {"id": "conversion_rate", "label": "Conversion Rate",      "enabled": True,  "order": 4},
        {"id": "anomaly_log",     "label": "Anomaly Log",          "enabled": True,  "order": 5},
        {"id": "benchmark",       "label": "Industry Benchmark",   "enabled": True,  "order": 6},
        {"id": "demand_forecast", "label": "Demand Forecast",      "enabled": False, "order": 7},
        {"id": "lost_sales",      "label": "Lost Sales Estimate",  "enabled": False, "order": 8},
    ],
    "admin": [
        {"id": "global_kpis",     "label": "Global KPIs",          "enabled": True,  "order": 1},
        {"id": "store_benchmark", "label": "Store Benchmarks",     "enabled": True,  "order": 2},
        {"id": "enterprise_ops",  "label": "Enterprise Ops",       "enabled": True,  "order": 3},
        {"id": "api_usage",       "label": "API Usage",            "enabled": True,  "order": 4},
        {"id": "whitelabel_mgmt", "label": "Whitelabel Clients",   "enabled": True,  "order": 5},
        {"id": "compliance_all",  "label": "Compliance Overview",  "enabled": True,  "order": 6},
        {"id": "anomaly_log",     "label": "Anomaly Log",          "enabled": True,  "order": 7},
        {"id": "scheduled_rpts",  "label": "Scheduled Reports",    "enabled": True,  "order": 8},
    ],
}

# In-memory role widget overrides
_role_widget_overrides: dict = {}

# In-memory language settings per store
_store_language: dict = {}


# ── Whitelabel ────────────────────────────────────────────────────────────────

class WhitelabelReq(BaseModel):
    client_id:     str
    brand_name:    str = "RetailVision"
    logo_url:      Optional[str] = None
    primary_color: str = "#0057ff"
    accent_color:  str = "#7c3aed"
    custom_domain: Optional[str] = None
    support_email: Optional[str] = None
    language:      str = "en"


@router.get("/whitelabel")
def get_whitelabel(client_id: str = "default", db: Session = Depends(get_db)):
    cfg = db.query(WhitelabelConfig).filter(WhitelabelConfig.client_id == client_id).first()
    if not cfg:
        return {
            "client_id": client_id, "brand_name": "RetailVision",
            "primary_color": "#0057ff", "accent_color": "#7c3aed",
            "language": "en", "active": True, "configured": False,
        }
    return {
        "client_id":     cfg.client_id,
        "brand_name":    cfg.brand_name,
        "logo_url":      cfg.logo_url,
        "primary_color": cfg.primary_color,
        "accent_color":  cfg.accent_color,
        "custom_domain": cfg.custom_domain,
        "support_email": cfg.support_email,
        "language":      cfg.language,
        "active":        cfg.active,
        "configured":    True,
    }


@router.post("/whitelabel")
def save_whitelabel(req: WhitelabelReq, db: Session = Depends(get_db)):
    cfg = db.query(WhitelabelConfig).filter(WhitelabelConfig.client_id == req.client_id).first()
    if cfg:
        for k, v in req.model_dump().items():
            setattr(cfg, k, v)
    else:
        cfg = WhitelabelConfig(**req.model_dump())
        db.add(cfg)
    db.commit()
    return {"status": "saved", "client_id": req.client_id, "brand_name": req.brand_name}


@router.get("/saas/clients")
def list_saas_clients(db: Session = Depends(get_db)):
    clients = db.query(WhitelabelConfig).all()
    return {
        "total": len(clients),
        "clients": [
            {"client_id": c.client_id, "brand_name": c.brand_name,
             "custom_domain": c.custom_domain, "active": c.active,
             "created_at": str(c.created_at)[:10]}
            for c in clients
        ],
    }


# ── API Keys ──────────────────────────────────────────────────────────────────

class APIKeyReq(BaseModel):
    store_id:  str = "store_1"
    key_name:  str
    scopes:    list = ["read"]   # read | write | alerts | admin


@router.post("/api-keys")
def generate_api_key(req: APIKeyReq, db: Session = Depends(get_db)):
    """Generate a new API key. Returns the full key ONCE — store it securely."""
    raw_key    = "rvai_" + secrets.token_urlsafe(32)
    key_hash   = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12]

    key = APIKey(
        store_id=req.store_id,
        key_name=req.key_name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=req.scopes,
    )
    db.add(key); db.commit(); db.refresh(key)

    return {
        "status":     "created",
        "id":         key.id,
        "key_name":   req.key_name,
        "api_key":    raw_key,   # shown ONCE
        "key_prefix": key_prefix,
        "scopes":     req.scopes,
        "warning":    "Store this key securely — it will NOT be shown again.",
    }


@router.get("/api-keys")
def list_api_keys(store_id: str = "store_1", db: Session = Depends(get_db)):
    keys = db.query(APIKey).filter(APIKey.store_id == store_id).all()
    return {
        "total": len(keys),
        "keys": [
            {
                "id":         k.id,
                "key_name":   k.key_name,
                "key_prefix": k.key_prefix + "...",
                "scopes":     k.scopes,
                "active":     k.active,
                "last_used":  str(k.last_used)[:16] if k.last_used else "Never",
                "created_at": str(k.created_at)[:10],
            }
            for k in keys
        ],
        "api_docs_url": "http://localhost:8000/docs",
        "webhook_url":  "http://localhost:8000/ws/broadcast",
    }


@router.delete("/api-keys/{key_id}")
def revoke_api_key(key_id: int, db: Session = Depends(get_db)):
    key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not key:
        raise HTTPException(404, "API key not found")
    key.active = False
    db.commit()
    return {"status": "revoked", "id": key_id}


@router.post("/api-keys/{key_id}/test")
def test_api_key(key_id: int, db: Session = Depends(get_db)):
    """Simulate a third-party API call using this key."""
    key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not key:
        raise HTTPException(404, "API key not found")
    if not key.active:
        return {"status": "error", "message": "API key is revoked"}
    key.last_used = datetime.datetime.utcnow()
    db.commit()
    return {
        "status":    "success",
        "key_name":  key.key_name,
        "scopes":    key.scopes,
        "test_response": {
            "endpoint": "/jobs/",
            "method":   "GET",
            "result":   "200 OK — API key valid and working",
        },
        "integration_examples": {
            "curl":    f'curl -H "X-API-Key: {key.key_prefix}..." http://localhost:8000/jobs/',
            "python":  f'requests.get("http://localhost:8000/jobs/", headers={{"X-API-Key": "{key.key_prefix}..."}})',
            "webhook": 'POST http://localhost:8000/ws/broadcast {"type":"alert","message":"..."}',
        },
    }


# ── Language ──────────────────────────────────────────────────────────────────

@router.get("/languages")
def list_languages():
    return {
        "supported": SUPPORTED_LANGUAGES,
        "default":   "en",
        "total":     len(SUPPORTED_LANGUAGES),
    }


@router.post("/language/set")
def set_language(store_id: str = "store_1", language: str = "en"):
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(400, f"Unsupported language. Choose from: {list(SUPPORTED_LANGUAGES.keys())}")
    _store_language[store_id] = language
    return {"status": "set", "store_id": store_id, "language": language, "name": SUPPORTED_LANGUAGES[language]["name"]}


@router.get("/language/current")
def get_current_language(store_id: str = "store_1"):
    lang = _store_language.get(store_id, "en")
    return {"store_id": store_id, "language": lang, **SUPPORTED_LANGUAGES.get(lang, {})}


# ── Role Dashboards ───────────────────────────────────────────────────────────

class RoleDashboardReq(BaseModel):
    role:    str   # store_manager | analyst | admin
    widgets: list  # list of widget configs


@router.get("/role-dashboards")
def get_role_dashboards(role: Optional[str] = None):
    if role:
        widgets = _role_widget_overrides.get(role, DEFAULT_ROLE_WIDGETS.get(role, []))
        return {"role": role, "widgets": widgets}
    result = {}
    for r in ["store_manager", "analyst", "admin"]:
        result[r] = _role_widget_overrides.get(r, DEFAULT_ROLE_WIDGETS.get(r, []))
    return {"dashboards": result, "roles": list(result.keys())}


@router.post("/role-dashboards")
def save_role_dashboard(req: RoleDashboardReq):
    if req.role not in ("store_manager", "analyst", "admin"):
        raise HTTPException(400, "role must be store_manager | analyst | admin")
    _role_widget_overrides[req.role] = req.widgets
    return {"status": "saved", "role": req.role, "widget_count": len(req.widgets)}
