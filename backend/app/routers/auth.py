"""
routers/auth.py — JWT Authentication for Retail AI System
Demo users work offline without DB.
"""
import jwt
import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

SECRET = "retail-ai-secret-2024"
ALGO   = "HS256"

# ── Demo users (fallback when no DB) ──────────────────────────────────────────
DEMO_USERS = {
    "manager@store.com": {
        "id": "u1", "name": "Rahul Sharma", "email": "manager@store.com",
        "password": "manager123", "role": "store_manager", "store": "Store #1 - Andheri"
    },
    "analyst@store.com": {
        "id": "u2", "name": "Priya Patel", "email": "analyst@store.com",
        "password": "analyst123", "role": "analyst", "store": "All Stores"
    },
    "admin@store.com": {
        "id": "u3", "name": "Admin User", "email": "admin@store.com",
        "password": "admin123", "role": "admin", "store": "HQ"
    },
}

STORE_INFO = {
    "store_manager": {"name": "RetailVision India", "plan": "Pro",   "store": "Store #1 - Andheri"},
    "analyst":       {"name": "RetailVision India", "plan": "Pro",   "store": "All Stores"},
    "admin":         {"name": "RetailVision HQ",    "plan": "Enterprise", "store": "HQ"},
}


def make_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGO)


class LoginReq(BaseModel):
    email: str
    password: str

class RegisterReq(BaseModel):
    name: str
    email: str
    password: str
    store: str = "New Store"
    role: str = "store_manager"
    plan: str = "starter"


@router.post("/login")
def login(req: LoginReq):
    u = DEMO_USERS.get(req.email)
    if not u or u["password"] != req.password:
        raise HTTPException(401, "Invalid credentials")
    token = make_token(u["id"], u["role"])
    company = STORE_INFO.get(u["role"], {"name": "RetailVision", "plan": "Starter", "store": u.get("store","")})
    return {
        "access_token": token,
        "user": {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"], "store": u.get("store","")},
        "company": company,
    }


@router.post("/register")
def register(req: RegisterReq):
    token = make_token("new_" + req.email[:6], req.role)
    return {
        "access_token": token,
        "user": {"id": "new", "name": req.name, "email": req.email, "role": req.role, "store": req.store},
        "company": {"name": req.store, "plan": req.plan, "store": req.store},
    }


@router.get("/me")
def me():
    return {"status": "ok"}
