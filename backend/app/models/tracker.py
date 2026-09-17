"""
tracker.py — Robust Person Tracker for Retail CCTV
"""

import time
import math
import numpy as np
from collections import deque

import supervision as sv

from app.config import (
    IDENTITY_TTL, IDENTITY_DIST_THRESH,
    BYTETRACK_TRACK_THRESH, BYTETRACK_MATCH_THRESH,
    BYTETRACK_TRACK_BUFFER, BYTETRACK_FRAME_RATE, BYTETRACK_MIN_FRAMES,
)


class KalmanBoxSmoother:
    def __init__(self, process_noise: float = 1e-2, measurement_noise: float = 10.0):
        self.Q = process_noise
        self.R = measurement_noise
        self.x = None
        self.P = None

    def update(self, box: np.ndarray) -> np.ndarray:
        box = np.array(box, dtype=float)
        if self.x is None:
            self.x = box.copy()
            self.P = np.ones(4) * 10.0
            return box.astype(int)
        P_pred = self.P + self.Q
        K = P_pred / (P_pred + self.R)
        self.x = self.x + K * (box - self.x)
        self.P = (1 - K) * P_pred
        return self.x.astype(int)


class LoopAwareIdentityManager:
    def __init__(self, ttl: float = IDENTITY_TTL, dist_thresh: float = IDENTITY_DIST_THRESH,
                 min_hits: int = BYTETRACK_MIN_FRAMES):
        self.ttl         = ttl
        self.dist_thresh = dist_thresh
        self.min_hits    = min_hits
        self.dead_tracks: deque = deque()
        self.active_map:  dict  = {}
        self.hit_count:   dict  = {}
        self.confirmed:   set   = set()
        self.next_global_id: int = 1

    @staticmethod
    def _center(box):
        x1, y1, x2, y2 = box
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @staticmethod
    def _iou(a, b):
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2); iy2 = min(ay2, by2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        if inter == 0:
            return 0.0
        area_a = (ax2 - ax1) * (ay2 - ay1)
        area_b = (bx2 - bx1) * (by2 - by1)
        return inter / (area_a + area_b - inter + 1e-6)

    def _prune_dead(self):
        now = time.time()
        while self.dead_tracks and (now - self.dead_tracks[0]["time"]) > self.ttl:
            self.dead_tracks.popleft()

    def assign_id(self, tracker_id: int, box) -> int:
        self.hit_count[tracker_id] = self.hit_count.get(tracker_id, 0) + 1
        if tracker_id in self.active_map:
            gid = self.active_map[tracker_id]
            if self.hit_count[tracker_id] >= self.min_hits:
                self.confirmed.add(gid)
            return gid
        self._prune_dead()
        now = time.time()
        cx, cy = self._center(box)
        best_match = None
        best_score = float("inf")
        for item in self.dead_tracks:
            if (now - item["time"]) > self.ttl:
                continue
            px, py = item["center"]
            dist = math.hypot(cx - px, cy - py)
            if dist > self.dist_thresh:
                continue
            iou = self._iou(box, item["box"])
            score = dist * (1.0 - iou * 0.5)
            if score < best_score:
                best_score = score
                best_match = item
        if best_match:
            gid = best_match["gid"]
            self.active_map[tracker_id] = gid
            self.dead_tracks.remove(best_match)
            self.confirmed.add(gid)
            return gid
        gid = self.next_global_id
        self.next_global_id += 1
        self.active_map[tracker_id] = gid
        if self.hit_count[tracker_id] >= self.min_hits:
            self.confirmed.add(gid)
        return gid

    def mark_dead(self, tracker_id: int, box) -> None:
        if tracker_id not in self.active_map:
            self.hit_count.pop(tracker_id, None)
            return
        self.dead_tracks.append({
            "gid":    self.active_map.pop(tracker_id),
            "center": self._center(box),
            "box":    list(box),
            "time":   time.time(),
        })
        self.hit_count.pop(tracker_id, None)

    @property
    def total_unique(self) -> int:
        return len(self.confirmed)


class Tracker:
    def __init__(self):
        self.tracker = sv.ByteTrack(
            track_activation_threshold=BYTETRACK_TRACK_THRESH,
            lost_track_buffer=BYTETRACK_TRACK_BUFFER,
            minimum_matching_threshold=BYTETRACK_MATCH_THRESH,
            frame_rate=BYTETRACK_FRAME_RATE,
        )
        self.id_manager  = LoopAwareIdentityManager()
        self.smoothers:  dict = {}
        self.prev_active: dict = {}

    def update(self, detections: sv.Detections) -> sv.Detections:
        if len(detections) == 0:
            detections.tracker_id = np.array([], dtype=int)
            detections.data["global_id"] = np.array([], dtype=int)
            for tid in set(self.prev_active):
                self.id_manager.mark_dead(tid, self.prev_active[tid])
                self.smoothers.pop(tid, None)
            self.prev_active = {}
            return detections

        tracked = self.tracker.update_with_detections(detections)
        current_active: dict = {}
        global_ids: list     = []
        smoothed_boxes: list = []

        if len(tracked) > 0 and tracked.tracker_id is not None and len(tracked.tracker_id) == len(tracked):
            for box, tid in zip(tracked.xyxy, tracked.tracker_id):
                tid_int  = int(tid)
                box_ints = list(map(int, box))
                if tid_int not in self.smoothers:
                    self.smoothers[tid_int] = KalmanBoxSmoother()
                smooth_box = self.smoothers[tid_int].update(box_ints)
                smoothed_boxes.append(smooth_box)
                gid = self.id_manager.assign_id(tid_int, smooth_box)
                current_active[tid_int] = smooth_box
                global_ids.append(gid)
            tracked.xyxy = np.array(smoothed_boxes, dtype=np.float32)
            tracked.data["global_id"] = np.array(global_ids, dtype=int)
        else:
            tracked.tracker_id = None
            tracked.data["global_id"] = np.array([], dtype=int)

        disappeared = set(self.prev_active) - set(current_active)
        for tid in disappeared:
            self.id_manager.mark_dead(tid, self.prev_active[tid])
            self.smoothers.pop(tid, None)

        self.prev_active = current_active
        return tracked

    @property
    def total_unique_people(self) -> int:
        return self.id_manager.total_unique
