"""
footfall.py — Polygon-zone based Footfall Counter.

Entry zone aur Exit zone alag-alag polygons hain.
Jab koi person entry zone mein aata hai → entry count.
Jab koi person exit zone mein aata hai → exit count.
"""

import time
from typing import Dict, List, Optional
import numpy as np
import cv2


def _point_in_polygon(cx: int, cy: int, polygon: np.ndarray) -> bool:
    """Returns True if point (cx, cy) is inside the polygon."""
    return cv2.pointPolygonTest(polygon, (float(cx), float(cy)), False) >= 0


class FootfallCounter:

    def __init__(
        self,
        entry_zone: Optional[np.ndarray] = None,
        exit_zone: Optional[np.ndarray] = None,
        # Legacy line params kept for backward compat (ignored if zones provided)
        height: int = 720,
        entry_line_ratio: float = 0.40,
        exit_line_ratio: float = 0.70,
        entry_direction: str = "down",
        exit_direction: str = "up",
    ):
        self.entry_zone: Optional[np.ndarray] = entry_zone
        self.exit_zone: Optional[np.ndarray] = exit_zone

        # Legacy line fallback
        self.entry_line_y: int = int(height * entry_line_ratio)
        self.exit_line_y: int = int(height * exit_line_ratio)
        self.entry_direction = entry_direction
        self.exit_direction = exit_direction

        self.use_zones = entry_zone is not None or exit_zone is not None

        # Track which zone each person is currently in
        self._in_entry: set = set()   # tracker_ids currently inside entry zone
        self._in_exit: set = set()    # tracker_ids currently inside exit zone

        # Line-mode last positions
        self.last_cy: Dict[int, int] = {}

        self.entry_count: int = 0
        self.exit_count: int = 0
        self.inside_ids: set = set()
        self.crossing_log: List[dict] = []

    def _line_crossed(self, prev_y: int, cy: int, line_y: int, direction: str) -> bool:
        if direction == "down":
            return prev_y < line_y <= cy
        else:
            return prev_y >= line_y > cy

    def update(self, tracked, time_sec: float = 0.0) -> None:
        if len(tracked) == 0 or tracked.tracker_id is None:
            return

        global_ids = tracked.data.get("global_id", None)

        for i, (box, tid) in enumerate(zip(tracked.xyxy, tracked.tracker_id)):
            tid = int(tid)
            x1, y1, x2, y2 = box
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            gid = int(global_ids[i]) if global_ids is not None and i < len(global_ids) else tid

            if self.use_zones:
                # Entry zone check
                if self.entry_zone is not None:
                    now_in_entry = _point_in_polygon(cx, cy, self.entry_zone)
                    was_in_entry = tid in self._in_entry
                    if now_in_entry and not was_in_entry:
                        self.entry_count += 1
                        self.inside_ids.add(gid)
                        self.crossing_log.append({"type": "entry", "global_id": gid, "timestamp": time_sec})
                        self._in_entry.add(tid)
                    elif not now_in_entry and was_in_entry:
                        self._in_entry.discard(tid)

                # Exit zone check
                if self.exit_zone is not None:
                    now_in_exit = _point_in_polygon(cx, cy, self.exit_zone)
                    was_in_exit = tid in self._in_exit
                    if now_in_exit and not was_in_exit:
                        self.exit_count += 1
                        self.inside_ids.discard(gid)
                        self.crossing_log.append({"type": "exit", "global_id": gid, "timestamp": time_sec})
                        self._in_exit.add(tid)
                    elif not now_in_exit and was_in_exit:
                        self._in_exit.discard(tid)
            else:
                # Legacy line mode
                if tid in self.last_cy:
                    prev_y = self.last_cy[tid]
                    if self._line_crossed(prev_y, cy, self.entry_line_y, self.entry_direction):
                        self.entry_count += 1
                        self.inside_ids.add(gid)
                        self.crossing_log.append({"type": "entry", "global_id": gid, "timestamp": time_sec})
                    elif self._line_crossed(prev_y, cy, self.exit_line_y, self.exit_direction):
                        self.exit_count += 1
                        self.inside_ids.discard(gid)
                        self.crossing_log.append({"type": "exit", "global_id": gid, "timestamp": time_sec})
                self.last_cy[tid] = cy

    def get_counts(self) -> dict:
        return {
            "entries": self.entry_count,
            "exits": self.exit_count,
            "currently_inside": len(self.inside_ids),
        }

    def get_crossing_log(self) -> List[dict]:
        return self.crossing_log

    @property
    def line_position(self) -> int:
        return self.entry_line_y

    @property
    def exit_line_position(self) -> int:
        return self.exit_line_y
