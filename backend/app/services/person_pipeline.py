"""
app/services/person_pipeline.py

Exact pipeline as per diagram:

CAMERA
  ↓
PERSON DETECTION (YOLO)
  ↓
PERSON TRACKING (ByteTrack → global_id)
  ↓
PERSON ID (global_id → stable across cameras)
  ↓
┌──────────────────────────────────┐
↓                                  ↓
FACE DETECTION               BODY TRACKING
(InsightFace)                (Re-ID embedding)
↓                                  ↓
Face available?            Face unavailable?
↓                                  ↓
Identity/Attributes ←── Persistent Track ID (name_anchor)
│                                  │
└──────────────┬───────────────────┘
               ↓
          ZONE ENGINE
               ↓
  ┌────────────┼────────────┐
  ↓            ↓            ↓
Dwell        Journey      Heatmap
Time         Analysis     Analytics
  ↓            ↓            ↓
         DASHBOARD
"""

import time
import logging
import numpy as np
import cv2
from collections import deque, defaultdict
from typing import Optional

from app.reid.global_registry import global_registry
from app.reid.name_anchor import name_anchor
from app.reid.feature_extractor import extract as reid_extract
from app.reid.employee_db import employee_db
from app.services.alert_engine import alert_engine
from app.config import SHOW_CONFIDENCE, SHOW_ZONE_LABEL, SHOW_DWELL_TIMER, SHOW_TRAIL, TRAIL_LENGTH, LOITERING_EXEMPT_CAMERAS

log = logging.getLogger("PersonPipeline")

# Zone grid config
ZONE_ROWS = ["Top", "Mid", "Bottom"]
ZONE_COLS = ["Left", "Center", "Right"]

# Face detection every N frames (CPU saver)
FACE_EVERY_N = 1  # check every frame for faster detection

# Re-ID embedding every N frames (reduces CPU, avoids noisy embeddings)
REID_EVERY_N = 3


class PersonState:
    """Per-person state maintained across frames."""
    __slots__ = (
        "global_id", "bbox", "name", "is_staff",
        "zone", "dwell_start", "trail",
        "face_confirmed", "face_sim", "_body_emb",
        "age", "gender",
    )

    def __init__(self, global_id: int, bbox: list):
        self.global_id     = global_id
        self.bbox          = bbox
        self.name:    Optional[str]   = None
        self.is_staff:     bool       = False
        self.zone:    Optional[str]   = None
        self.dwell_start:  float      = time.time()
        self.trail:        deque      = deque(maxlen=TRAIL_LENGTH)
        self.face_confirmed: bool     = False
        self.face_sim:     float      = 0.0
        self._body_emb                = None
        self.age:          str        = ""
        self.gender:       str        = ""


class PersonPipeline:
    """
    Single class that owns the full pipeline per camera.
    analytics_service.py calls process_frame() each frame.
    """

    def __init__(self, camera_id: str, camera_name: str = "", store_id: str = "store_1"):
        self.camera_id   = camera_id
        self.camera_name = camera_name
        self.store_id    = store_id

        # Active persons this camera: global_id → PersonState
        self._persons: dict[int, PersonState] = {}

        # Heatmap (set on first frame)
        self._heatmap: Optional[np.ndarray] = None

        # Frame counter
        self._frame_n = 0

        # Face recognizer (lazy load)
        self._face_recognizer = None

        # Vote buffer owned here — keyed by global_id, not track_id
        # FaceRecognizer.vote_buffer is NOT used by this pipeline
        self._vote_buffer: defaultdict = defaultdict(lambda: deque(maxlen=3))

        # Load enrolled face embeddings into employee_db
        from app.face.config import EMBEDDINGS_FILE
        from app.face.config import SIMILARITY_THRESHOLD as _SIM_THRESH
        from app.face.config import SIMILARITY_GAP as _SIM_GAP
        self._sim_thresh = _SIM_THRESH
        self._sim_gap    = _SIM_GAP
        employee_db.load_enrolled(EMBEDDINGS_FILE)

        # Frontend-drawn polygon zones — loaded once at startup per camera
        self._zones: list = []
        self._load_zones()

    # ── Face recognizer lazy load ─────────────────────────────────────────────

    def _get_fr(self):
        if self._face_recognizer is None:
            try:
                from app.face.recognizer import FaceRecognizer
                fr = FaceRecognizer.get()
                if fr.index is not None:
                    self._face_recognizer = fr
            except Exception:
                pass
        return self._face_recognizer

    # ── Polygon zone loader ───────────────────────────────────────────────────

    def _load_zones(self):
        """Fetch frontend-drawn polygon zones from Node.js for this camera.
        Polygon format: [{"x": 0.1, "y": 0.2}, ...] normalized 0-1.
        Stored in threshold_config.camera_code to link zone → camera.
        """
        try:
            import urllib.request as _ur
            import json as _json
            from app.config import NODEJS_BACKEND_URL, NODEJS_AI_API_KEY
            url = f"{NODEJS_BACKEND_URL}/api/ai-ingest/zones?camera_code={self.camera_id}"
            req = _ur.Request(url, headers={"x-ai-service-key": NODEJS_AI_API_KEY})
            with _ur.urlopen(req, timeout=3) as r:
                data = _json.loads(r.read())
            self._zones = [
                {
                    "name":    z["zone_code"],
                    "label":   z["name"],
                    "type":    z["zone_type"],
                    "polygon": z["polygon"],   # [{"x":0.1,"y":0.2}, ...]
                }
                for z in data.get("zones", [])
                if z.get("polygon") and len(z["polygon"]) >= 3
            ]
            log.info(f"[{self.camera_id}] {len(self._zones)} polygon zone(s) loaded.")
        except Exception as e:
            self._zones = []
            log.debug(f"[{self.camera_id}] Zone load skipped (grid fallback): {e}")

    def reload_zones(self):
        """Hot-reload zones without restarting camera thread."""
        self._load_zones()
        log.info(f"[{self.camera_id}] Zones reloaded: {len(self._zones)} polygon(s).")

    # ── Zone assignment ───────────────────────────────────────────────────────

    @staticmethod
    def _zone(cx_n: float, cy_n: float) -> str:
        """Fallback 3x3 grid zone when no polygon matches."""
        row = ZONE_ROWS[min(int(cy_n * 3), 2)]
        col = ZONE_COLS[min(int(cx_n * 3), 2)]
        return f"{row}-{col}"

    def _zone_from_polygons(self, cx_n: float, cy_n: float, w: int, h: int) -> Optional[str]:
        """cv2.pointPolygonTest — returns zone_code of first matching polygon, else None."""
        pt = (float(cx_n * w), float(cy_n * h))
        for z in self._zones:
            try:
                poly = np.array(
                    [[p["x"] * w, p["y"] * h] for p in z["polygon"]],
                    dtype=np.float32
                )
                if cv2.pointPolygonTest(poly, pt, False) >= 0:
                    return z["name"]   # zone_code e.g. "cam2_entrance"
            except Exception:
                continue
        return None

    def _draw_zones(self, frame: np.ndarray):
        """Draw all polygon zones on frame — for visual debugging."""
        h, w = frame.shape[:2]
        for z in self._zones:
            try:
                pts = np.array(
                    [[int(p["x"] * w), int(p["y"] * h)] for p in z["polygon"]],
                    dtype=np.int32
                )
                cv2.polylines(frame, [pts], isClosed=True, color=(0, 255, 255), thickness=1)
                cx = int(np.mean(pts[:, 0]))
                cy = int(np.mean(pts[:, 1]))
                cv2.putText(frame, z["label"], (cx - 20, cy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
            except Exception:
                continue

    # ── IoU helper ────────────────────────────────────────────────────────────

    @staticmethod
    def _iou(a: list, b: list) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        union = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
        return inter / union if union > 0 else 0.0

    # ── Main entry point ──────────────────────────────────────────────────────

    def process_frame(
        self,
        frame: np.ndarray,
        tracked,           # sv.Detections with tracker_id + global_id
        run_reid: bool = True,
        face_frame: np.ndarray = None,  # high-res main stream frame for face recognition
    ) -> dict:
        """
        Full pipeline for one frame.
        Returns live analytics dict for dashboard.
        """
        self._frame_n += 1
        now = time.time()
        h_f, w_f = frame.shape[:2]

        # Init heatmap
        if self._heatmap is None:
            self._heatmap = np.zeros((h_f // 4, w_f // 4), dtype=np.float32)

        # ── STEP 1: PERSON DETECTION + TRACKING (done by caller via YOLO+ByteTrack)
        # tracked = sv.Detections already passed in

        active_gids: set[int] = set()
        zone_counts: dict[str, int] = {}

        if tracked.tracker_id is not None and len(tracked) > 0:
            gids_arr = tracked.data.get("global_id", [])

            # ── STEP 2: PERSON ID — assign stable global_id via Re-ID ─────────
            for i, (box, tid) in enumerate(zip(tracked.xyxy, tracked.tracker_id)):
                tid_int = int(tid)
                box_i   = list(map(int, box))

                if run_reid and self._frame_n % REID_EVERY_N == 0:
                    emb       = reid_extract(frame, box)
                    global_id = global_registry.assign(self.camera_id, tid_int, emb)
                else:
                    # Non-reid frame: reuse existing mapping, don't create new ID
                    existing  = global_registry.get_active_on_camera(self.camera_id)
                    global_id = existing.get(tid_int)
                    if global_id is None:
                        # First time seeing this tid — must do reid now
                        emb       = reid_extract(frame, box)
                        global_id = global_registry.assign(self.camera_id, tid_int, emb)

                active_gids.add(global_id)

                # Create or update PersonState
                if global_id not in self._persons:
                    self._persons[global_id] = PersonState(global_id, box_i)
                    _log_movement(global_id, self.camera_id, self.camera_name, "appeared",
                                  None, box_i)

                ps       = self._persons[global_id]
                ps.bbox  = box_i

                x1, y1, x2, y2 = box_i
                cx_px = (x1 + x2) // 2
                cy_px = (y1 + y2) // 2
                cx_n  = cx_px / w_f
                cy_n  = cy_px / h_f

                # Trail
                ps.trail.append((cx_px, cy_px))

                # Heatmap
                hx = min(int(cx_n * self._heatmap.shape[1]), self._heatmap.shape[1] - 1)
                hy = min(int(cy_n * self._heatmap.shape[0]), self._heatmap.shape[0] - 1)
                self._heatmap[hy, hx] += 1.0

                # ── STEP 3: ZONE ENGINE ───────────────────────────────────────
                # Polygon zones (frontend-drawn) first, fallback to 3x3 grid
                new_zone = (
                    self._zone_from_polygons(cx_n, cy_n, w_f, h_f)
                    or self._zone(cx_n, cy_n)
                )
                if ps.zone != new_zone:
                    if ps.zone:
                        alert_engine.person_exited_zone(global_id, ps.zone)
                    alert_engine.person_entered_zone(global_id, new_zone,
                                                     self.camera_id, ps.is_staff)
                    ps.zone = new_zone

                zone_counts[new_zone] = zone_counts.get(new_zone, 0) + 1

                # ── STEP 4: FACE DETECTION (cam6 only, every N frames) ─────────
                if self.camera_id == "cam6" and self._frame_n % FACE_EVERY_N == 0:
                    self._run_face(face_frame if face_frame is not None else frame, ps, global_id)

                # ── STEP 5: BODY TRACKING — name from anchor/cache only ────────
                if not ps.face_confirmed:
                    # Sirf cache se naam lo — body alone se identify nahi karenge
                    anchored = name_anchor.get_name(global_id)
                    if anchored:
                        ps.name     = anchored
                        ps.is_staff = True
                else:
                    name_anchor.touch(global_id, self.camera_id)
                    body_emb = reid_extract(frame, ps.bbox)
                    ps._body_emb = body_emb
                    employee_db.update_body(global_id, body_emb, self.camera_id)

                # ── STEP 6: ALERT ENGINE checks ───────────────────────────────
                if self._frame_n % 30 == 0 and self.camera_id not in LOITERING_EXEMPT_CAMERAS:
                    alert_engine.check_loitering(
                        global_id, ps.zone or "", self.camera_id,
                        ps.is_staff or bool(ps.name), self.store_id
                    )
                if self.camera_id == "cam3" and self._frame_n % 15 == 0:
                    dwell = round(now - ps.dwell_start, 1)
                    alert_engine.check_shelf_interaction(
                        global_id, ps.zone or "", self.camera_id, dwell, self.store_id
                    )
                if self._frame_n % 30 == 0 and not ps.face_confirmed and ps.name is None:
                    alert_engine.check_stranger(global_id, self.camera_id, self.store_id)

                # ── STEP 7: DRAW on frame ─────────────────────────────────────
                self._draw_person(frame, ps)

        # Draw polygon zone boundaries on frame (cyan outlines)
        if self._zones:
            self._draw_zones(frame)

        # ── Handle disappeared persons ────────────────────────────────────────
        disappeared = set(self._persons.keys()) - active_gids
        # Build reverse map: gid → local_tid (before releasing)
        active_cam = global_registry.get_active_on_camera(self.camera_id)
        gid_to_tid = {g: t for t, g in active_cam.items()}
        for gid in disappeared:
            ps = self._persons.pop(gid)
            if ps.zone:
                alert_engine.person_exited_zone(gid, ps.zone)
            alert_engine.person_left_store(gid, self.camera_id, self.store_id)
            _log_movement(gid, self.camera_id, self.camera_name, "disappeared", ps.zone, ps.bbox)
            tid = gid_to_tid.get(gid)
            if tid is not None:
                global_registry.release(self.camera_id, tid)

        # ── Zone alerts ───────────────────────────────────────────────────────
        for z, cnt in zone_counts.items():
            alert_engine.check_crowd(z, cnt, self.camera_id, self.store_id)
            if any(k in z.lower() for k in ("billing", "checkout", "bottom-right")):
                alert_engine.check_queue(z, cnt, self.camera_id, self.store_id)

        # ── Analytics dict for dashboard ──────────────────────────────────────
        dwell_times = [round(now - ps.dwell_start, 1) for ps in self._persons.values()]
        return {
            "currently_inside": len(active_gids),
            "zone_current":     zone_counts,
            "dwell_avg_sec":    round(sum(dwell_times) / len(dwell_times), 1) if dwell_times else 0,
            "dwell_max_sec":    max(dwell_times) if dwell_times else 0,
            "active_journeys":  alert_engine.get_active_journeys(),
            "heatmap":          self._heatmap,
            "persons":          [self._person_dict(ps) for ps in self._persons.values()],
        }

    # ── Face detection + identity resolution ─────────────────────────────────

    def _run_face(self, frame: np.ndarray, ps: PersonState, global_id: int):
        fr = self._get_fr()
        if fr is None:
            return
        try:
            # Crop top 55% of person bbox — head/face region — then upscale for InsightFace
            bx1, by1, bx2, by2 = ps.bbox
            crop_h = int((by2 - by1) * 0.55)
            face_crop = frame[max(0, by1):by1 + crop_h, max(0, bx1):bx2]
            if face_crop.size == 0:
                return
            # Upscale if too small for InsightFace
            fh, fw = face_crop.shape[:2]
            if fw < 112 or fh < 112:
                scale = max(112 / fw, 112 / fh)
                face_crop = cv2.resize(face_crop, (int(fw * scale), int(fh * scale)),
                                       interpolation=cv2.INTER_CUBIC)
            # CLAHE on crop if dark
            if cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY).mean() < 80:
                lab = cv2.cvtColor(face_crop, cv2.COLOR_BGR2LAB)
                l, a, b = cv2.split(lab)
                cl = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(l)
                face_crop = cv2.cvtColor(cv2.merge([cl, a, b]), cv2.COLOR_LAB2BGR)

            faces = fr.app.get(face_crop)
            for face in faces:
                fx1, fy1, fx2, fy2 = map(int, face.bbox)

                # Remap face bbox back to original frame coords for drawing
                orig_fx1 = bx1 + fx1
                orig_fy1 = by1 + fy1
                orig_fx2 = bx1 + fx2
                orig_fy2 = by1 + fy2

                # Cyan box on face (original frame coords)
                cv2.rectangle(frame, (orig_fx1, orig_fy1), (orig_fx2, orig_fy2), (255, 255, 0), 2)

                face_emb = face.normed_embedding

                # Age / gender from InsightFace genderage model
                if hasattr(face, 'age') and face.age:
                    ps.age = str(int(face.age))
                if hasattr(face, 'gender') and face.gender is not None:
                    ps.gender = "M" if face.gender == 1 else "F"

                # Already confirmed — just touch anchor, skip re-voting
                if ps.face_confirmed:
                    name_anchor.touch(global_id, self.camera_id)
                    break

                # Vote buffer (owned by PersonPipeline, keyed by global_id)
                # 3 frames mein 2 baar same name + sim >= 0.62 + gap >= 0.06 → confirm
                raw_name, sim = fr._recognize(face_emb)
                self._vote_buffer[global_id].append(raw_name)
                votes = self._vote_buffer[global_id]
                if len(votes) < 3:
                    continue
                name_votes = [v for v in votes if v != "Unknown"]
                if len(name_votes) < 2 or sim < self._sim_thresh:
                    continue
                confirmed = max(set(name_votes), key=name_votes.count)

                # Confirm in employee_db (face + body combined)
                employee_db.confirm_face(global_id, confirmed, face_emb, sim,
                                         camera_id=self.camera_id)

                ps.name           = confirmed
                ps.face_confirmed = True
                ps.face_sim       = sim
                ps.is_staff       = True
                name_anchor.set_name(global_id, confirmed, confidence=sim,
                                     camera_id=self.camera_id)
                _save_attendance(confirmed, sim, self.camera_id, self.store_id)
                break
        except Exception as e:
            log.debug(f"Face detection error: {e}")

    # ── Draw ─────────────────────────────────────────────────────────────────

    def _draw_person(self, frame: np.ndarray, ps: PersonState):
        x1, y1, x2, y2 = ps.bbox
        dwell = int(time.time() - ps.dwell_start)

        if ps.face_confirmed:
            color = (0, 220, 0)
        elif ps.name:
            color = (0, 200, 120)
        else:
            color = (255, 180, 0)

        thickness = 3 if dwell >= 30 else 2
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

        # Build label: name + confidence + age/gender + dwell
        parts = [ps.name or f"P-{ps.global_id}"]
        if SHOW_CONFIDENCE and ps.face_confirmed and ps.face_sim > 0:
            parts.append(f"{ps.face_sim:.2f}")
        if ps.age:
            parts.append(f"{ps.age}{ps.gender}")
        if SHOW_DWELL_TIMER:
            parts.append(f"{dwell}s")
        label = "  ".join(parts)

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 6, y1), color, -1)
        cv2.putText(frame, label, (x1 + 3, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 0, 0), 1, cv2.LINE_AA)

        # Trail
        if SHOW_TRAIL:
            pts = list(ps.trail)
            for j in range(1, len(pts)):
                alpha = j / len(pts)
                c = tuple(int(v * alpha) for v in color)
                cv2.line(frame, pts[j-1], pts[j], c, 2)

        # Zone label below box
        if SHOW_ZONE_LABEL and ps.zone:
            cv2.putText(frame, ps.zone, (x1, y2 + 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)

    def _person_dict(self, ps: PersonState) -> dict:
        return {
            "global_id":      ps.global_id,
            "name":           ps.name or "Unknown",
            "is_staff":       ps.is_staff,
            "face_confirmed": ps.face_confirmed,
            "face_sim":       round(ps.face_sim, 3),
            "age":            ps.age,
            "gender":         ps.gender,
            "zone":           ps.zone,
            "dwell_sec":      round(time.time() - ps.dwell_start, 1),
            "bbox":           ps.bbox,
        }

    def get_heatmap(self) -> Optional[np.ndarray]:
        return self._heatmap

    def reset(self):
        self._persons.clear()
        self._vote_buffer.clear()
        self._heatmap = None
        self._frame_n = 0


# ── DB helpers ────────────────────────────────────────────────────────────────

def _save_attendance(name: str, sim: float, camera_id: str, store_id: str):
    import threading
    def _run():
        try:
            from datetime import datetime, timezone, timedelta
            from app.services.pg_sync import sync_face_attendance
            IST = timezone(timedelta(hours=5, minutes=30))
            now_ist = datetime.now(IST)
            today = now_ist.strftime("%Y-%m-%d")
            sync_face_attendance(name, today, now_ist.isoformat(), sim, camera_id, store_id)
            log.info(f"Attendance synced to PostgreSQL: {name} on {today}")
        except Exception as e:
            log.debug(f"Attendance save failed: {e}")
    threading.Thread(target=_run, daemon=True).start()


def _log_movement(global_id, camera_id, camera_name, event_type, zone, box):
    import threading
    def _run():
        try:
            from app.services.pg_sync import sync_movement
            sync_movement(global_id, camera_id, camera_name or "", event_type,
                          zone or "", list(map(int, box)) if box else [], "store_1")
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()
