"""
core/recognizer.py — Face Recognition + Production-Ready Face Tracking Engine

Tracking Pipeline:
  Frame → InsightFace Detection → Track Matching (IoU + Kalman) → Track Management
  → Vote-based Recognition → Attendance Logging → Visualization + Analytics

Track States:
  NEW → ACTIVE → TEMPORARILY_LOST → REMOVED
"""

import os
import time
import math
import logging
import numpy as np
import cv2
import faiss
from collections import defaultdict, deque
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from insightface.app import FaceAnalysis

from core.config import (
    INSIGHTFACE_MODEL, DET_SIZE, EMBEDDINGS_FILE,
    SIMILARITY_THRESHOLD, VOTE_FRAMES, MIN_FACE_SIZE, BLUR_THRESHOLD,
    ATTENDANCE_COOLDOWN_SEC, MAX_LOST_FRAMES, MIN_HITS_TO_CONFIRM, IOU_MATCH_THRESHOLD,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("FaceTracker")


# ── Track State ───────────────────────────────────────────────────────────────
class TrackStatus(str, Enum):
    NEW              = "new"
    ACTIVE           = "active"
    TEMPORARILY_LOST = "lost"
    REMOVED          = "removed"


# ── Kalman Box Smoother ───────────────────────────────────────────────────────
class KalmanSmoother:
    """Per-track 1-D Kalman filter on each bbox coordinate."""
    def __init__(self, process_noise: float = 1e-2, measurement_noise: float = 5.0):
        self.Q = process_noise
        self.R = measurement_noise
        self.x: Optional[np.ndarray] = None
        self.P: Optional[np.ndarray] = None

    def update(self, box: list) -> list:
        box = np.array(box, dtype=float)
        if self.x is None:
            self.x = box.copy()
            self.P = np.ones(4) * 10.0
            return box.astype(int).tolist()
        P_pred = self.P + self.Q
        K      = P_pred / (P_pred + self.R)
        self.x = self.x + K * (box - self.x)
        self.P = (1 - K) * P_pred
        return self.x.astype(int).tolist()

    def predict(self) -> Optional[list]:
        """Return last known position as prediction (constant velocity model)."""
        return self.x.astype(int).tolist() if self.x is not None else None


# ── Track ─────────────────────────────────────────────────────────────────────
@dataclass
class Track:
    track_id:    int
    bbox:        list                          # [x1, y1, x2, y2]
    confidence:  float = 0.0
    status:      TrackStatus = TrackStatus.NEW

    # Timing
    first_frame: int   = 0
    last_frame:  int   = 0
    frames_tracked: int = 0
    lost_frames: int   = 0
    created_at:  float = field(default_factory=time.time)

    # Recognition
    name:        str   = "Unknown"
    confirmed:   bool  = False
    sim:         float = 0.0
    vote_buffer: deque = field(default_factory=lambda: deque(maxlen=VOTE_FRAMES))

    # Kalman
    smoother:    KalmanSmoother = field(default_factory=KalmanSmoother)

    @property
    def center(self) -> tuple:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    @property
    def age_sec(self) -> float:
        return time.time() - self.created_at

    def to_dict(self) -> dict:
        return {
            "track_id":      self.track_id,
            "name":          self.name,
            "confidence":    round(self.confidence, 3),
            "sim":           round(self.sim, 3),
            "bbox":          self.bbox,
            "center":        [round(c) for c in self.center],
            "first_frame":   self.first_frame,
            "last_frame":    self.last_frame,
            "frames_tracked": self.frames_tracked,
            "status":        self.status.value,
            "confirmed":     self.confirmed,
            "age_sec":       round(self.age_sec, 1),
        }


# ── Face Recognizer + Tracker ─────────────────────────────────────────────────
class FaceRecognizer:
    def __init__(self):
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

        # InsightFace
        self.app = FaceAnalysis(name=INSIGHTFACE_MODEL, providers=["CPUExecutionProvider"])
        self.app.prepare(ctx_id=0, det_size=DET_SIZE)

        # FAISS recognition index
        self.db_names:      list              = []
        self.db_embeddings: Optional[np.ndarray] = None
        self.index:         Optional[faiss.Index] = None
        self.load_embeddings()

        # Track registry
        self._tracks:       dict[int, Track] = {}   # track_id → Track
        self._next_id:      int              = 1
        self._frame_num:    int              = 0
        self._removed:      list[Track]      = []   # archive

        # Attendance
        self.attendance_log: dict[str, datetime] = {}
        self.visitor_log:    dict[int, datetime] = {}
        self.events:         list[dict]          = []

        # FPS
        self._fps_times: deque = deque(maxlen=30)

    # ── Embeddings ────────────────────────────────────────────────────────────

    def load_embeddings(self):
        try:
            with np.load(EMBEDDINGS_FILE, allow_pickle=True) as db:
                self.db_names      = db["names"].tolist()
                self.db_embeddings = db["embeddings"].astype("float32")
            self._build_index()
            log.info(f"Loaded {len(self.db_names)} person(s): {self.db_names}")
        except FileNotFoundError:
            log.warning("No embeddings file — run enroll first")
            self.db_names = []; self.db_embeddings = None; self.index = None

    def _build_index(self):
        if self.db_embeddings is None or len(self.db_embeddings) == 0:
            self.index = None
            return
        emb = self.db_embeddings.copy()
        faiss.normalize_L2(emb)
        self.index = faiss.IndexFlatIP(emb.shape[1])
        self.index.add(emb)

    def reload(self):
        self.load_embeddings()

    # ── Quality check ─────────────────────────────────────────────────────────

    def _quality_ok(self, img: np.ndarray, face) -> bool:
        x1, y1, x2, y2 = map(int, face.bbox)
        if (x2 - x1) < MIN_FACE_SIZE or (y2 - y1) < MIN_FACE_SIZE:
            return False
        crop = img[max(0, y1):y2, max(0, x1):x2]
        if crop.size == 0:
            return False
        blur = cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
        return blur >= BLUR_THRESHOLD

    # ── IoU ───────────────────────────────────────────────────────────────────

    @staticmethod
    def _iou(a: list, b: list) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        union = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
        return inter / union if union > 0 else 0.0

    # ── Track Management ──────────────────────────────────────────────────────

    def _match_detections(self, detections: list[dict]) -> dict[int, int]:
        """
        Hungarian-style greedy IoU matching.
        Returns {det_index: track_id}
        Uses predicted (Kalman) box for lost tracks.
        """
        active_tracks = {
            tid: t for tid, t in self._tracks.items()
            if t.status in (TrackStatus.NEW, TrackStatus.ACTIVE, TrackStatus.TEMPORARILY_LOST)
        }
        if not active_tracks or not detections:
            return {}

        # Build IoU matrix
        track_ids  = list(active_tracks.keys())
        iou_matrix = np.zeros((len(detections), len(track_ids)), dtype=float)

        for di, det in enumerate(detections):
            for ti, tid in enumerate(track_ids):
                t = active_tracks[tid]
                pred_box = t.smoother.predict() or t.bbox
                iou_matrix[di, ti] = self._iou(det["bbox"], pred_box)

        # Greedy match — highest IoU first
        matched: dict[int, int] = {}
        used_tracks: set = set()
        pairs = sorted(
            [(di, ti) for di in range(len(detections)) for ti in range(len(track_ids))],
            key=lambda p: iou_matrix[p[0], p[1]], reverse=True
        )
        for di, ti in pairs:
            if iou_matrix[di, ti] < IOU_MATCH_THRESHOLD:
                break
            if di in matched or track_ids[ti] in used_tracks:
                continue
            matched[di] = track_ids[ti]
            used_tracks.add(track_ids[ti])

        return matched

    def _update_track(self, track: Track, det: dict):
        """Update existing track with new detection."""
        smooth_box       = track.smoother.update(det["bbox"])
        track.bbox       = smooth_box
        track.confidence = det["confidence"]
        track.last_frame = self._frame_num
        track.frames_tracked += 1
        track.lost_frames    = 0

        if track.status == TrackStatus.TEMPORARILY_LOST:
            log.info(f"Track Recovered: ID={track.track_id} name={track.name}")

        if track.frames_tracked >= MIN_HITS_TO_CONFIRM:
            track.status = TrackStatus.ACTIVE
        else:
            track.status = TrackStatus.NEW

    def _create_track(self, det: dict) -> Track:
        """Create a new track for an unmatched detection."""
        tid   = self._next_id
        self._next_id += 1
        smooth_box = KalmanSmoother().update(det["bbox"])
        t = Track(
            track_id    = tid,
            bbox        = smooth_box,
            confidence  = det["confidence"],
            first_frame = self._frame_num,
            last_frame  = self._frame_num,
            frames_tracked = 1,
        )
        t.smoother.update(det["bbox"])
        self._tracks[tid] = t
        log.info(f"New Track Created: ID={tid}")
        return t

    def _age_lost_tracks(self, matched_track_ids: set):
        """Increment lost_frames for unmatched tracks, remove stale ones."""
        for tid, t in list(self._tracks.items()):
            if tid in matched_track_ids:
                continue
            if t.status == TrackStatus.REMOVED:
                continue
            t.lost_frames += 1
            t.status = TrackStatus.TEMPORARILY_LOST

            if t.lost_frames > MAX_LOST_FRAMES:
                t.status = TrackStatus.REMOVED
                self._removed.append(t)
                del self._tracks[tid]
                log.info(f"Track Removed: ID={tid} name={t.name} frames={t.frames_tracked}")

    # ── Recognition ───────────────────────────────────────────────────────────

    def _recognize(self, emb: np.ndarray) -> tuple[str, float]:
        if self.index is None:
            return "Unknown", 0.0
        emb32 = emb.astype("float32").reshape(1, -1)
        faiss.normalize_L2(emb32)
        k = min(len(self.db_names), 5)
        sims, idxs = self.index.search(emb32, k)
        # Best match per person (handles multiple clusters per person)
        best: dict[str, float] = {}
        for sim, idx in zip(sims[0], idxs[0]):
            name = self.db_names[int(idx)]
            if name not in best or sim > best[name]:
                best[name] = float(sim)
        top_name = max(best, key=best.get)
        top_sim  = best[top_name]
        if top_sim >= SIMILARITY_THRESHOLD:
            return top_name, top_sim
        return "Unknown", top_sim

    # ── Attendance Logging ────────────────────────────────────────────────────

    def _log_event(self, name: str, track_id: int, sim: float):
        now = datetime.now()
        if name == "Unknown":
            if track_id not in self.visitor_log:
                self.visitor_log[track_id] = now
                self.events.append({
                    "type": "visitor", "name": "Unknown",
                    "track_id": track_id, "sim": round(sim, 3),
                    "timestamp": now.isoformat(),
                })
                log.info(f"VISITOR  track={track_id}")
        else:
            last = self.attendance_log.get(name)
            if last is None or (now - last).seconds >= ATTENDANCE_COOLDOWN_SEC:
                self.attendance_log[name] = now
                self.events.append({
                    "type": "employee", "name": name,
                    "track_id": track_id, "sim": round(sim, 3),
                    "timestamp": now.isoformat(),
                })
                log.info(f"EMPLOYEE {name}  sim={sim:.3f}  track={track_id}")

    # ── Visualization ─────────────────────────────────────────────────────────

    def _draw_track(self, frame: np.ndarray, track: Track):
        x1, y1, x2, y2 = track.bbox
        color = {
            TrackStatus.NEW:              (0, 200, 255),
            TrackStatus.ACTIVE:           (0, 210, 0),
            TrackStatus.TEMPORARILY_LOST: (0, 100, 255),
            TrackStatus.REMOVED:          (80, 80, 80),
        }.get(track.status, (200, 200, 200))

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        label_name = track.name if track.confirmed else "..."
        label = f"ID:{track.track_id} {label_name}"
        if track.confirmed and track.sim > 0:
            label += f" {track.sim:.2f}"

        # Background for label
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
        cv2.putText(frame, label, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)

    def _draw_hud(self, frame: np.ndarray, fps: float):
        active  = sum(1 for t in self._tracks.values() if t.status == TrackStatus.ACTIVE)
        lost    = sum(1 for t in self._tracks.values() if t.status == TrackStatus.TEMPORARILY_LOST)
        hud = [
            f"FPS: {fps:.1f}",
            f"Faces: {len(self._tracks)}",
            f"Active: {active}  Lost: {lost}",
            f"Total Unique: {self._next_id - 1}",
        ]
        for i, line in enumerate(hud):
            cv2.putText(frame, line, (10, 25 + i * 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, line, (10, 25 + i * 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)

    # ── Main process_frame ────────────────────────────────────────────────────

    def process_frame(self, frame: np.ndarray) -> tuple[np.ndarray, list]:
        """
        Full pipeline: Detection → Tracking → Recognition → Visualization.
        Returns annotated frame + list of active track dicts.
        """
        t0 = time.perf_counter()
        self._frame_num += 1
        self._fps_times.append(t0)

        # FPS
        fps = (len(self._fps_times) - 1) / (self._fps_times[-1] - self._fps_times[0]) \
              if len(self._fps_times) > 1 else 0.0

        # ── Detection ─────────────────────────────────────────────────────────
        faces = self.app.get(frame)
        detections = []
        for face in faces:
            x1, y1, x2, y2 = map(int, face.bbox)
            if not self._quality_ok(frame, face):
                continue
            detections.append({
                "bbox":       [x1, y1, x2, y2],
                "confidence": float(getattr(face, "det_score", 0.9)),
                "embedding":  face.normed_embedding,
            })

        # ── Track Matching ────────────────────────────────────────────────────
        matched = self._match_detections(detections)   # {det_idx: track_id}
        matched_track_ids = set(matched.values())

        results = []

        for di, det in enumerate(detections):
            if di in matched:
                track = self._tracks[matched[di]]
                self._update_track(track, det)
            else:
                track = self._create_track(det)

            # ── Recognition on this track ──────────────────────────────────
            raw_name, sim = self._recognize(det["embedding"])
            track.vote_buffer.append(raw_name)
            votes = track.vote_buffer

            if len(votes) >= VOTE_FRAMES:
                confirmed_name = max(set(votes), key=votes.count)
                if not track.confirmed or sim > track.sim:
                    track.name      = confirmed_name
                    track.sim       = sim
                    track.confirmed = True
                self._log_event(confirmed_name, track.track_id, sim)

            results.append(track.to_dict())

        # ── Age lost tracks ───────────────────────────────────────────────────
        self._age_lost_tracks(matched_track_ids | {t.track_id for t in [self._create_track.__self__] if False})
        self._age_lost_tracks(matched_track_ids)

        # ── Draw all active tracks ────────────────────────────────────────────
        for track in self._tracks.values():
            if track.status != TrackStatus.REMOVED:
                self._draw_track(frame, track)

        self._draw_hud(frame, fps)

        log.debug(f"Frame {self._frame_num} | faces={len(detections)} | "
                  f"tracks={len(self._tracks)} | fps={fps:.1f} | "
                  f"latency={(time.perf_counter()-t0)*1000:.1f}ms")

        return frame, results

    # ── Analytics ─────────────────────────────────────────────────────────────

    def get_analytics(self) -> dict:
        active   = [t for t in self._tracks.values() if t.status == TrackStatus.ACTIVE]
        lost     = [t for t in self._tracks.values() if t.status == TrackStatus.TEMPORARILY_LOST]
        all_done = self._removed + list(self._tracks.values())
        avg_dur  = (sum(t.frames_tracked for t in all_done) / len(all_done)) if all_done else 0

        return {
            "current_faces":       len(self._tracks),
            "active_tracks":       len(active),
            "lost_tracks":         len(lost),
            "total_unique_tracks": self._next_id - 1,
            "removed_tracks":      len(self._removed),
            "avg_frames_tracked":  round(avg_dur, 1),
            "frame_number":        self._frame_num,
        }

    def get_events(self) -> list:
        return list(self.events)

    def reset_session(self):
        self._tracks.clear()
        self._removed.clear()
        self.vote_buffer    = defaultdict(lambda: deque(maxlen=VOTE_FRAMES))
        self.visitor_log.clear()
        self.events.clear()
        self._next_id   = 1
        self._frame_num = 0
        log.info("Session reset")
