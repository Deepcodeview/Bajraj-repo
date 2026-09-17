"""
dwell.py — Per-person dwell time tracker using global IDs.

Fixes over original:
- Uses global_id (stable) not local tracker_id (resets on re-entry)
- Records final dwell for people who have left (not just active ones)
- Handles re-entrants: accumulates time across multiple visits
- Provides per-person breakdown in addition to average
"""

import time
from typing import Dict, List


class DwellTracker:
    """
    Tracks how long each unique person (by global_id) spends in the scene.
    Accumulates time across multiple visits for the same global_id.
    """

    def __init__(self):
        # global_id → wall-clock time when they first appeared this visit
        self._visit_start: Dict[int, float] = {}

        # global_id → total accumulated seconds (finalised visits)
        self._accumulated: Dict[int, float] = {}

    # ── public API ───────────────────────────
    def update(self, tracked) -> None:
        """
        Pass sv.Detections with .data["global_id"].
        Call once per frame.
        """
        if len(tracked) == 0:
            return

        global_ids = tracked.data.get("global_id", None)
        if global_ids is None or len(global_ids) == 0:
            return

        now = time.time()
        seen_this_frame = set()

        for gid in global_ids:
            gid = int(gid)
            seen_this_frame.add(gid)

            if gid not in self._visit_start:
                self._visit_start[gid] = now

        # Finalise tracks that disappeared this frame
        disappeared = set(self._visit_start) - seen_this_frame
        for gid in disappeared:
            elapsed = now - self._visit_start.pop(gid)
            self._accumulated[gid] = self._accumulated.get(gid, 0.0) + elapsed

    def finalise_all(self) -> None:
        """
        Call at end of video to flush all still-active visit timers.
        """
        now = time.time()
        for gid, start in list(self._visit_start.items()):
            elapsed = now - start
            self._accumulated[gid] = self._accumulated.get(gid, 0.0) + elapsed
        self._visit_start.clear()

    def get_average_dwell(self) -> float:
        """Average dwell time in seconds across all people seen."""
        self.finalise_all()
        all_times = list(self._accumulated.values())
        if not all_times:
            return 0.0
        return sum(all_times) / len(all_times)

    def get_per_person_dwell(self) -> Dict[int, float]:
        """Returns {global_id: total_seconds} for every person."""
        self.finalise_all()
        return dict(self._accumulated)

    def get_summary(self) -> dict:
        """Returns avg, min, max, and total unique people tracked."""
        per_person = self.get_per_person_dwell()
        if not per_person:
            return {"avg": 0.0, "min": 0.0, "max": 0.0, "total_people_tracked": 0}
        values = list(per_person.values())
        return {
            "avg_sec": round(sum(values) / len(values), 2),
            "min_sec": round(min(values), 2),
            "max_sec": round(max(values), 2),
            "total_people_tracked": len(values),
        }