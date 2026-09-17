"""
reid/name_anchor.py — Face Name → Global ID Anchor Registry
"""

import threading
import time
import numpy as np
from typing import Optional


class NameAnchorRegistry:
    def __init__(self, ttl: float = 3600.0):
        self._lock  = threading.Lock()
        self._ttl   = ttl
        self._anchors: dict = {}

    def set_name(self, global_id: int, name: str, confidence: float = 1.0, camera_id: str = ""):
        with self._lock:
            existing = self._anchors.get(global_id)
            for other_gid, other_data in list(self._anchors.items()):
                if other_gid == global_id:
                    continue
                if other_data.get("name") == name:
                    if confidence > other_data.get("confidence", 0):
                        del self._anchors[other_gid]
                    else:
                        return
                    break
            if existing is None or confidence >= existing.get("confidence", 0):
                phone_fields = {k: existing[k] for k in ("phone_active", "phone_start_time", "phone_total_sec", "phone_sessions") if existing and k in existing}
                self._anchors[global_id] = {
                    "name":       name,
                    "last_seen":  time.time(),
                    "confidence": confidence,
                    "camera_id":  camera_id,
                    **phone_fields,
                }

    def get_name(self, global_id: int) -> Optional[str]:
        with self._lock:
            anchor = self._anchors.get(global_id)
            if anchor is None:
                return None
            if time.time() - anchor["last_seen"] > self._ttl:
                del self._anchors[global_id]
                return None
            anchor["last_seen"] = time.time()
            return anchor["name"]

    def touch(self, global_id: int, camera_id: str = ""):
        with self._lock:
            if global_id in self._anchors:
                self._anchors[global_id]["last_seen"] = time.time()
                self._anchors[global_id]["camera_id"] = camera_id

    def get_all(self) -> dict:
        with self._lock:
            now = time.time()
            return {
                gid: {**v, "age_sec": round(now - v["last_seen"])}
                for gid, v in self._anchors.items()
                if now - v["last_seen"] <= self._ttl
            }

    def clear(self):
        with self._lock:
            self._anchors.clear()

    def phone_start(self, global_id: int):
        with self._lock:
            anchor = self._anchors.get(global_id)
            if anchor is None:
                return
            if not anchor.get("phone_active"):
                anchor["phone_active"]     = True
                anchor["phone_start_time"] = time.time()
                anchor.setdefault("phone_total_sec", 0.0)
                anchor.setdefault("phone_sessions",  [])

    def phone_end(self, global_id: int):
        with self._lock:
            anchor = self._anchors.get(global_id)
            if anchor is None or not anchor.get("phone_active"):
                return
            duration = round(time.time() - anchor.get("phone_start_time", time.time()), 1)
            anchor["phone_active"] = False
            anchor["phone_total_sec"] = anchor.get("phone_total_sec", 0.0) + duration
            anchor.setdefault("phone_sessions", []).append({
                "start": anchor.get("phone_start_time", time.time()),
                "duration_sec": duration,
            })

    def get_phone_usage(self) -> list:
        with self._lock:
            now  = time.time()
            rows = []
            for gid, v in self._anchors.items():
                if now - v["last_seen"] > self._ttl:
                    continue
                total = v.get("phone_total_sec", 0.0)
                if v.get("phone_active"):
                    total += round(now - v["phone_start_time"], 1)
                if total > 0 or v.get("phone_active"):
                    rows.append({
                        "global_id":       gid,
                        "name":            v["name"],
                        "phone_active":    v.get("phone_active", False),
                        "phone_total_sec": round(total, 1),
                        "sessions":        len(v.get("phone_sessions", [])),
                        "last_camera":     v.get("camera_id", ""),
                    })
            return rows


name_anchor = NameAnchorRegistry()
