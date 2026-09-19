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
LOITERING_SEC          = 300  # dwell >= 300s → loitering (CAM-6, CAM-7, CAM-8)
CROWD_THRESHOLD        = 8    # people in one zone >= 8 → crowd alert
QUEUE_THRESHOLD        = 4    # people in billing zone >= 4 → queue alert
SHELF_INTERACT_SEC     = 10   # person near shelf > 10s → shelf interaction
SHELF_EMPTY_SEC        = 30   # shelf EMPTY/LOW STOCK sustained >= 30s → alert
PHONE_DETECT_THRESH    = 5    # phone detected >= 5 times for same person → alert
STRANGER_DETECT_THRESH = 5    # unknown face seen >= 5 times on same camera → alert
REPEAT_VISIT_DAYS      = 1    # same person seen again within N days → repeat visit
ALERT_COOLDOWN_SEC     = 60   # same alert type per zone per minute


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

        # camera_id → timestamp when shelf first went EMPTY/LOW STOCK
        self._shelf_empty_since: dict[str, float] = {}

        # (camera_id, global_id) → phone detection hit count
        self._phone_hits: dict[tuple, int] = {}

        # (camera_id, global_id) → unknown-face detection hit count
        self._stranger_hits: dict[tuple, int] = {}

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
            self._phone_hits    = {k: v for k, v in self._phone_hits.items()    if k[1] != global_id}
            self._stranger_hits = {k: v for k, v in self._stranger_hits.items() if k[1] != global_id}

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

    def check_shelf_empty(self, camera_id: str, status: str, store_id: str = "store_1"):
        """Call after each shelf detection. Fires when shelf stays EMPTY/LOW STOCK >= SHELF_EMPTY_SEC."""
        now = time.time()
        with self._lock:
            if status in ("EMPTY", "LOW STOCK"):
                if camera_id not in self._shelf_empty_since:
                    self._shelf_empty_since[camera_id] = now
                duration = now - self._shelf_empty_since[camera_id]
            else:
                self._shelf_empty_since.pop(camera_id, None)
                return
        if duration >= SHELF_EMPTY_SEC:
            self._fire_alert(
                alert_type="shelf_empty",
                severity="HIGH",
                camera_id=camera_id,
                zone=None,
                global_id=None,
                message=f"Shelf {status} on {camera_id} for {int(duration)}s",
                store_id=store_id,
                metadata={"status": status, "duration_sec": round(duration, 1)},
            )

    def check_phone_usage(self, global_id: int, camera_id: str, store_id: str = "store_1"):
        """Increment hit count; fire alert when >= PHONE_DETECT_THRESH detections."""
        key = (camera_id, global_id)
        with self._lock:
            self._phone_hits[key] = self._phone_hits.get(key, 0) + 1
            count = self._phone_hits[key]
        if count >= PHONE_DETECT_THRESH:
            self._fire_alert(
                alert_type="phone_usage",
                severity="MEDIUM",
                camera_id=camera_id,
                zone=None,
                global_id=global_id,
                message=f"Person {global_id} using phone on {camera_id} ({count} detections)",
                store_id=store_id,
                metadata={"detections": count},
            )

    def check_stranger(self, global_id: int, camera_id: str, store_id: str = "store_1"):
        """Increment unknown-face hit count; fire alert when >= STRANGER_DETECT_THRESH."""
        key = (camera_id, global_id)
        with self._lock:
            self._stranger_hits[key] = self._stranger_hits.get(key, 0) + 1
            count = self._stranger_hits[key]
        if count >= STRANGER_DETECT_THRESH:
            self._fire_alert(
                alert_type="stranger",
                severity="HIGH",
                camera_id=camera_id,
                zone=None,
                global_id=global_id,
                message=f"Unknown person {global_id} seen {count} times on {camera_id}",
                store_id=store_id,
                metadata={"detections": count},
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
            from app.services.pg_sync import sync_alert
            sync_alert(alert_type, severity, camera_id or "", zone or "",
                       global_id, message, metadata or {}, store_id)
        except Exception as e:
            log.debug(f"Alert DB save failed: {e}")
    _db_executor.submit(_run)


def _save_loitering(global_id, camera_id, zone, dwell_sec, store_id):
    def _run():
        try:
            from app.services.pg_sync import sync_alert
            sync_alert("loitering", "HIGH", camera_id, zone or "",
                       global_id, f"Loitering {int(dwell_sec)}s",
                       {"dwell_sec": round(dwell_sec, 1)}, store_id)
        except Exception as e:
            log.debug(f"Loitering DB save failed: {e}")
    _db_executor.submit(_run)


def _save_shelf_interaction(global_id, camera_id, zone, interaction, dwell_sec, store_id):
    def _run():
        try:
            from app.services.pg_sync import sync_alert
            sync_alert("shelf_interaction", "LOW", camera_id, zone or "",
                       global_id, f"Shelf {interaction} {int(dwell_sec)}s",
                       {"interaction": interaction, "dwell_sec": round(dwell_sec, 1)}, store_id)
        except Exception as e:
            log.debug(f"Shelf interaction DB save failed: {e}")
    _db_executor.submit(_run)


def _save_journey(global_id, journey, total_dwell_sec, zones_visited,
                  entry_time, is_repeat, store_id):
    def _run():
        try:
            from app.services.pg_sync import sync_journey
            from datetime import datetime
            exit_now = datetime.utcnow()
            sync_journey(
                global_id, journey, round(total_dwell_sec, 1), zones_visited,
                entry_time.isoformat() if entry_time else None,
                exit_now.isoformat(), store_id,
            )
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
