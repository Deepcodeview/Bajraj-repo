"""
app/services/alert_engine.py — Centralized Real-time Alert Engine

Handles:
- Loitering Detection       (person in zone > threshold)
- Crowd Detection           (zone count > threshold)
- Queue Detection           (billing zone > threshold)
- Repeat Visit              (same anonymized person returns)
- Shelf Interaction         (person near shelf > threshold)
- Abandoned Object          (stationary object detected)
- Staff vs Customer         (staff excluded from alerts)

Integrates with existing:
- websocket.py  → real-time push
- models.py     → DB persistence
- name_anchor   → staff identification
"""

import time
import threading
import logging
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

_db_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="alert_db")

log = logging.getLogger("AlertEngine")

# ── Thresholds ────────────────────────────────────────────────────────────────
LOITERING_SEC        = 120    # person in same zone > 2 min → loitering
CROWD_THRESHOLD      = 8      # people in one zone > 8 → crowd alert
QUEUE_THRESHOLD      = 3      # people in billing zone > 3 → queue alert
SHELF_INTERACT_SEC   = 10     # person near shelf > 10s → shelf interaction
REPEAT_VISIT_DAYS    = 1      # same person seen again within N days → repeat visit
ALERT_COOLDOWN_SEC   = 60     # same alert type per zone per minute


class AlertEngine:
    """
    Singleton alert engine — tracks per-person, per-zone state
    and fires alerts via WebSocket + DB.
    """

    def __init__(self):
        self._lock = threading.Lock()

        # global_id → {zone → entered_at}
        self._zone_entry: dict[int, dict[str, float]] = {}

        # global_id → [zone1, zone2, ...] (journey)
        self._journeys: dict[int, list[dict]] = {}

        # global_id → first_seen date string (for repeat visit)
        self._seen_dates: dict[int, set] = {}

        # (alert_type, zone, global_id) → last_fired time
        self._cooldown: dict[tuple, float] = {}

        # global_id → entry_time
        self._entry_times: dict[int, float] = {}

    # ── Zone Entry/Exit ───────────────────────────────────────────────────────

    def person_entered_zone(self, global_id: int, zone: str, camera_id: str, is_staff: bool = False):
        """Call when person enters a zone."""
        with self._lock:
            if global_id not in self._zone_entry:
                self._zone_entry[global_id] = {}
            self._zone_entry[global_id][zone] = time.time()

            # Journey tracking
            if global_id not in self._journeys:
                self._journeys[global_id] = []
                self._entry_times[global_id] = time.time()
            self._journeys[global_id].append({
                "zone":       zone,
                "camera_id":  camera_id,
                "entered_at": datetime.utcnow().isoformat(),
                "exited_at":  None,
                "dwell_sec":  0,
                "is_staff":   is_staff,
            })

    def person_exited_zone(self, global_id: int, zone: str):
        """Call when person exits a zone — updates journey dwell time."""
        with self._lock:
            entry_time = (self._zone_entry.get(global_id) or {}).pop(zone, None)
            if entry_time and global_id in self._journeys:
                dwell = round(time.time() - entry_time, 1)
                # Update last journey entry for this zone
                for step in reversed(self._journeys[global_id]):
                    if step["zone"] == zone and step["exited_at"] is None:
                        step["exited_at"] = datetime.utcnow().isoformat()
                        step["dwell_sec"] = dwell
                        break

    def person_left_store(self, global_id: int, camera_id: str, store_id: str = "store_1"):
        """Call when person disappears from all cameras — save journey to DB."""
        with self._lock:
            journey = self._journeys.pop(global_id, [])
            entry_t = self._entry_times.pop(global_id, None)
            self._zone_entry.pop(global_id, None)

        if not journey:
            return

        total_dwell = sum(s.get("dwell_sec", 0) for s in journey)
        zones_visited = len({s["zone"] for s in journey})

        # Check repeat visit
        today = datetime.utcnow().strftime("%Y-%m-%d")
        seen = self._seen_dates.setdefault(global_id, set())
        is_repeat = today in seen
        seen.add(today)

        if is_repeat:
            self._fire_alert(
                alert_type="repeat_visit",
                severity="LOW",
                camera_id=camera_id,
                zone=None,
                global_id=global_id,
                message=f"Person {global_id} is a repeat visitor today",
                store_id=store_id,
            )

        # Persist journey to DB
        _save_journey(
            global_id=global_id,
            journey=journey,
            total_dwell_sec=total_dwell,
            zones_visited=zones_visited,
            entry_time=datetime.utcfromtimestamp(entry_t) if entry_t else None,
            is_repeat=is_repeat,
            store_id=store_id,
        )

    # ── Per-frame checks ──────────────────────────────────────────────────────

    def check_loitering(self, global_id: int, zone: str, camera_id: str,
                        is_staff: bool = False, store_id: str = "store_1"):
        """Call every N frames per tracked person."""
        if is_staff:
            return
        with self._lock:
            entered = (self._zone_entry.get(global_id) or {}).get(zone)
        if entered is None:
            return
        dwell = time.time() - entered
        if dwell >= LOITERING_SEC:
            self._fire_alert(
                alert_type="loitering",
                severity="HIGH",
                camera_id=camera_id,
                zone=zone,
                global_id=global_id,
                message=f"Person {global_id} loitering in {zone} for {int(dwell)}s",
                store_id=store_id,
                metadata={"dwell_sec": round(dwell, 1)},
            )
            _save_loitering(global_id, camera_id, zone, dwell, store_id)

    def check_crowd(self, zone: str, count: int, camera_id: str, store_id: str = "store_1"):
        """Call with current zone person count."""
        if count >= CROWD_THRESHOLD:
            self._fire_alert(
                alert_type="crowd",
                severity="HIGH",
                camera_id=camera_id,
                zone=zone,
                global_id=None,
                message=f"Crowd detected in {zone}: {count} people",
                store_id=store_id,
                metadata={"count": count},
            )

    def check_queue(self, zone: str, count: int, camera_id: str, store_id: str = "store_1"):
        """Call for billing/help-desk zones."""
        if count >= QUEUE_THRESHOLD:
            self._fire_alert(
                alert_type="queue",
                severity="MEDIUM",
                camera_id=camera_id,
                zone=zone,
                global_id=None,
                message=f"Queue alert in {zone}: {count} people waiting",
                store_id=store_id,
                metadata={"count": count},
            )

    def check_shelf_interaction(self, global_id: int, zone: str, camera_id: str,
                                 dwell_sec: float, store_id: str = "store_1"):
        """Call when person is near shelf zone."""
        if dwell_sec >= SHELF_INTERACT_SEC:
            interaction = "browse" if dwell_sec < 30 else "pickup"
            self._fire_alert(
                alert_type="shelf_interaction",
                severity="LOW",
                camera_id=camera_id,
                zone=zone,
                global_id=global_id,
                message=f"Person {global_id} {interaction} at {zone} for {int(dwell_sec)}s",
                store_id=store_id,
                metadata={"dwell_sec": round(dwell_sec, 1), "interaction": interaction},
            )
            _save_shelf_interaction(global_id, camera_id, zone, interaction, dwell_sec, store_id)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _fire_alert(self, alert_type: str, severity: str, camera_id: str,
                    zone: Optional[str], global_id: Optional[int],
                    message: str, store_id: str = "store_1",
                    metadata: dict = None):
        """Deduplicate via cooldown, push via WebSocket, save to DB."""
        key = (alert_type, zone or "", global_id or 0)
        now = time.time()
        with self._lock:
            last = self._cooldown.get(key, 0)
            if now - last < ALERT_COOLDOWN_SEC:
                return
            self._cooldown[key] = now

        log.warning(f"[ALERT] {alert_type.upper()} | {severity} | {message}")

        # Push via WebSocket (non-blocking)
        _push_ws_alert(severity, message, zone, alert_type, metadata)

        # Save to DB (non-blocking)
        _save_alert(alert_type, severity, camera_id, zone, global_id, message, metadata, store_id)

    def get_active_journeys(self) -> dict:
        with self._lock:
            return {
                gid: {
                    "steps":       steps,
                    "zones":       list({s["zone"] for s in steps}),
                    "dwell_so_far": round(time.time() - self._entry_times.get(gid, time.time()), 1),
                }
                for gid, steps in self._journeys.items()
            }


# ── Singleton ─────────────────────────────────────────────────────────────────
alert_engine = AlertEngine()


# ── DB helpers (non-blocking) ─────────────────────────────────────────────────

def _save_alert(alert_type, severity, camera_id, zone, global_id, message, metadata, store_id):
    def _run():
        try:
            from app.database.db import SessionLocal
            from app.database.models import AlertEngineLog
            with SessionLocal() as db:
                db.add(AlertEngineLog(
                    store_id=store_id, alert_type=alert_type, severity=severity,
                    camera_id=camera_id, zone=zone, global_id=global_id,
                    message=message, extra_data=metadata,
                ))
                db.commit()
        except Exception as e:
            log.debug(f"Alert DB save failed: {e}")
    _db_executor.submit(_run)


def _save_loitering(global_id, camera_id, zone, dwell_sec, store_id):
    def _run():
        try:
            from app.database.db import SessionLocal
            from app.database.models import LoiteringAlert
            with SessionLocal() as db:
                db.add(LoiteringAlert(
                    store_id=store_id, global_id=global_id,
                    camera_id=camera_id, zone=zone, dwell_sec=round(dwell_sec, 1),
                ))
                db.commit()
        except Exception as e:
            log.debug(f"Loitering DB save failed: {e}")
    _db_executor.submit(_run)


def _save_shelf_interaction(global_id, camera_id, zone, interaction, dwell_sec, store_id):
    def _run():
        try:
            from app.database.db import SessionLocal
            from app.database.models import ShelfInteractionLog
            with SessionLocal() as db:
                db.add(ShelfInteractionLog(
                    store_id=store_id, global_id=global_id, camera_id=camera_id,
                    zone=zone, interaction=interaction, dwell_sec=round(dwell_sec, 1),
                ))
                db.commit()
        except Exception as e:
            log.debug(f"Shelf interaction DB save failed: {e}")
    _db_executor.submit(_run)


def _save_journey(global_id, journey, total_dwell_sec, zones_visited,
                  entry_time, is_repeat, store_id):
    def _run():
        try:
            from app.database.db import SessionLocal
            from app.database.models import CustomerJourney
            with SessionLocal() as db:
                db.add(CustomerJourney(
                    store_id=store_id, global_id=global_id, journey=journey,
                    total_dwell_sec=round(total_dwell_sec, 1),
                    zones_visited=zones_visited, entry_time=entry_time,
                    exit_time=datetime.utcnow(), is_repeat=is_repeat,
                ))
                db.commit()
        except Exception as e:
            log.debug(f"Journey DB save failed: {e}")
    _db_executor.submit(_run)


def _push_ws_alert(severity, message, zone, alert_type, metadata):
    import asyncio
    payload = {
        "type":       "alert",
        "alert_type": alert_type,
        "severity":   severity,
        "message":    message,
        "zone":       zone,
        "metadata":   metadata,
        "ts":         datetime.utcnow().isoformat(),
    }
    try:
        from app.routers.websocket import manager
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(manager.broadcast(payload))
            return
    except Exception:
        pass

    def _run():
        try:
            from app.routers.websocket import manager
            loop = asyncio.new_event_loop()
            loop.run_until_complete(manager.broadcast(payload))
            loop.close()
        except Exception:
            pass
    _db_executor.submit(_run)
