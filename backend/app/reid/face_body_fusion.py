"""
reid/face_body_fusion.py — Face + Body Tracker Fusion

Flow:
  1. Person enters → Body tracker assigns Person_001 (global_id)
  2. Face detected → matched to "Vishal" → anchor: global_id=1 → "Vishal"
  3. Person turns sideways → face disappears → body tracker still holds global_id=1
  4. Person turns back → face detected again → matched to global_id=1 → "Vishal" ✅
  5. Attendance DB mein sirf ek baar save hota hai us din ke liye
"""

import time
import numpy as np
from typing import Optional


class FaceBodyFusion:
    """
    Face bbox aur Body tracker bbox ko IoU se match karta hai.
    Ek baar face se naam confirm hua → global_id ke saath anchor ho jata hai.
    Face na dikhe tab bhi naam body tracker se milta rehta hai.
    """

    def __init__(self, iou_threshold: float = 0.3):
        self.iou_threshold = iou_threshold
        # global_id → {"name": str, "confirmed_at": float, "sim": float}
        self._confirmed: dict[int, dict] = {}

    @staticmethod
    def _iou(a, b) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        union = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
        return inter / union if union > 0 else 0.0

    def match_face_to_track(
        self,
        face_bbox: list,
        tracked_boxes: list,   # list of [x1,y1,x2,y2]
        global_ids: list,      # corresponding global_ids
    ) -> Optional[int]:
        """
        Face bbox ko body tracker boxes se match karo IoU se.
        Best matching global_id return karo.
        """
        best_gid, best_iou = None, self.iou_threshold
        for box, gid in zip(tracked_boxes, global_ids):
            score = self._iou(face_bbox, box)
            if score > best_iou:
                best_iou = score
                best_gid = gid
        return best_gid

    def confirm_identity(self, global_id: int, name: str, sim: float):
        """Face se naam confirm hua → global_id ke saath anchor karo."""
        existing = self._confirmed.get(global_id)
        if existing is None or sim > existing["sim"]:
            self._confirmed[global_id] = {
                "name":         name,
                "confirmed_at": time.time(),
                "sim":          sim,
            }

    def get_name(self, global_id: int) -> Optional[str]:
        """Global_id ke liye naam lo — face na dikhe tab bhi."""
        entry = self._confirmed.get(global_id)
        return entry["name"] if entry else None

    def get_all_confirmed(self) -> dict:
        return {gid: v["name"] for gid, v in self._confirmed.items()}

    def clear(self):
        self._confirmed.clear()


# Singleton
face_body_fusion = FaceBodyFusion()
