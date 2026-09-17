"""
routers/websocket.py — Real-time WebSocket alerts for Retail AI
WS  /ws/alerts          → push alerts instantly to all connected clients
POST /ws/broadcast      → internal endpoint to push a message to all clients
GET  /ws/status         → how many clients connected
"""
import json
import asyncio
import datetime
from typing import Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/ws", tags=["websocket"])

# ── Connection Manager ────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self, message: dict):
        dead = set()
        payload = json.dumps(message)
        for ws in self.active:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.active.discard(ws)

    async def send_personal(self, ws: WebSocket, message: dict):
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            self.active.discard(ws)


manager = ConnectionManager()


# ── WebSocket Endpoint ────────────────────────────────────────────────────────

@router.websocket("/alerts")
async def ws_alerts(websocket: WebSocket):
    await manager.connect(websocket)
    # Send welcome + current stats
    await manager.send_personal(websocket, {
        "type":    "connected",
        "message": "RetailVision WebSocket connected",
        "clients": len(manager.active),
        "ts":      datetime.datetime.utcnow().isoformat(),
    })
    try:
        while True:
            # Keep alive — client can send pings
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await manager.send_personal(websocket, {
                        "type": "pong",
                        "ts":   datetime.datetime.utcnow().isoformat(),
                    })
            except Exception:
                pass
    except (WebSocketDisconnect, asyncio.TimeoutError):
        manager.disconnect(websocket)


# ── Broadcast endpoint (called internally from analytics pipeline) ────────────

@router.post("/broadcast")
async def broadcast_alert(payload: dict):
    """Push an alert to all connected WebSocket clients."""
    await manager.broadcast({
        "type":    "alert",
        "ts":      datetime.datetime.utcnow().isoformat(),
        **payload,
    })
    return {"sent_to": len(manager.active)}


@router.get("/status")
def ws_status():
    return {"connected_clients": len(manager.active)}


# ── Helper: push alert from sync code (used in analytics_service) ─────────────

def push_alert_sync(severity: str, message: str, zone: str = None, job_id: str = None):
    """
    Fire-and-forget alert push from synchronous code.
    Call this from analytics_service.py progress_cb.
    """
    import threading

    async def _push():
        await manager.broadcast({
            "type":     "alert",
            "severity": severity,
            "message":  message,
            "zone":     zone,
            "job_id":   job_id,
            "ts":       datetime.datetime.utcnow().isoformat(),
        })

    def _run():
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_push())
        loop.close()

    threading.Thread(target=_run, daemon=True).start()
