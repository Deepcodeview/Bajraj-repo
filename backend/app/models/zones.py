"""
zones.py — Zone analyzer with heatmap + per-zone dwell accumulation.

Improvements over original:
- Zones are configurable (pass custom polygons or use default thirds)
- Heatmap grid (16×9 cells) is accumulated across frames for a heat signature
- Per-zone unique person sets tracked (not just frame counts)
- get_zone_counts() safe when detections is empty
"""

import numpy as np
import supervision as sv
from typing import Dict, Optional, List


class ZoneAnalyzer:
    def __init__(
        self,
        width: int,
        height: int,
        custom_zones: Optional[Dict[str, np.ndarray]] = None,
        heatmap_cols: int = 16,
        heatmap_rows: int = 9,
    ):
        self.width = width
        self.height = height

        # ── Zone polygons ──────────────────────────
        if custom_zones:
            zone_polys = custom_zones
        else:
            # Default: vertical thirds
            w3 = width // 3
            zone_polys = {
                "Zone A": np.array([(0, 0),   (w3, 0),     (w3, height),     (0, height)]),
                "Zone B": np.array([(w3, 0),  (2*w3, 0),   (2*w3, height),   (w3, height)]),
                "Zone C": np.array([(2*w3, 0),(width, 0),  (width, height),  (2*w3, height)]),
            }

        self.zones: Dict[str, sv.PolygonZone] = {
            name: sv.PolygonZone(poly) for name, poly in zone_polys.items()
        }

        # ── Heatmap grid ────────────────────────────
        self.heatmap_cols = heatmap_cols
        self.heatmap_rows = heatmap_rows
        self.heatmap: np.ndarray = np.zeros((heatmap_rows, heatmap_cols), dtype=np.float32)

        # Per-zone unique global IDs seen
        self._zone_unique: Dict[str, set] = {name: set() for name in self.zones}

        self._zone_accumulator: Dict[str, int] = {name: 0 for name in self.zones}
        self.current_occupancy: Dict[str, int] = {name: 0 for name in self.zones}
        self._frame_count: int = 0

    # ── public API ───────────────────────────────
    def update(self, detections: sv.Detections) -> Dict[str, int]:
        """
        Update heatmap and zone counts for this frame.
        Returns per-zone frame count for this single frame.
        """
        self._frame_count += 1
        zone_counts: Dict[str, int] = {}
        
        # Pop global_id to avoid ValueError in supervision's PolygonZone.trigger validation
        global_ids = None
        if len(detections) > 0 and "global_id" in detections.data:
            global_ids = detections.data.pop("global_id")

        for name, zone in self.zones.items():
            if len(detections) > 0:
                mask = zone.trigger(detections)
                count = int(mask.sum())

                # Track unique visitors per zone
                if global_ids is not None:
                    for i, in_zone in enumerate(mask):
                        if in_zone and i < len(global_ids):
                            self._zone_unique[name].add(int(global_ids[i]))
            else:
                count = 0

            self._zone_accumulator[name] += count
            self.current_occupancy[name] = count
            zone_counts[name] = count

        # Restore global_id to detections.data
        if global_ids is not None:
            detections.data["global_id"] = global_ids

        # Update heatmap with centroid positions
        if len(detections) > 0:
            self._update_heatmap(detections.xyxy)

        return zone_counts

    def get_zone_counts(self, detections: sv.Detections) -> Dict[str, int]:
        """Legacy-compatible: just return per-zone count for this frame."""
        return self.update(detections)

    def get_summary(self) -> dict:
        """Return zone analytics summary."""
        avg_zones = {
            name: round(self._zone_accumulator[name] / self._frame_count, 2)
            if self._frame_count else 0
            for name in self.zones
        }
        unique_per_zone = {
            name: len(self._zone_unique[name]) for name in self.zones
        }
        most_popular = max(unique_per_zone, key=unique_per_zone.get) if unique_per_zone else None

        return {
            "avg_people_per_frame": avg_zones,
            "unique_visitors": unique_per_zone,
            "most_popular_zone": most_popular,
            "current_occupancy": self.current_occupancy,
            "heatmap": self.heatmap.tolist(),
        }

    def get_heatmap(self) -> np.ndarray:
        return self.heatmap.copy()

    # ── private ──────────────────────────────────
    def _update_heatmap(self, xyxy: np.ndarray) -> None:
        cell_w = self.width / self.heatmap_cols
        cell_h = self.height / self.heatmap_rows

        for box in xyxy:
            x1, y1, x2, y2 = box
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2

            col = min(int(cx / cell_w), self.heatmap_cols - 1)
            row = min(int(cy / cell_h), self.heatmap_rows - 1)

            self.heatmap[row, col] += 1