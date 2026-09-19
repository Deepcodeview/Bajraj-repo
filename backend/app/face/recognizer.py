"""
app/face/recognizer.py — Face Recognition Engine for smartstore
Features:
  1. Negative gallery        — false positive prevention
  2. Face lock               — stable name for N frames, no flickering
  3. CLAHE low-light         — auto contrast fix when frame is dark
  4. Per-frame single best   — only highest-confidence face gets named
  5. Attendance CSV export   — daily CSV saved to /reports/
  6. Stranger alert          — unknown person visible 5+ min triggers alert
  7. GPU auto-detect         — uses CUDA if available, fallback to CPU
  8. Node.js attendance POST — marks check-in/out in PostgreSQL via Node.js
  9. Re-ID / name anchor     — cross-camera identity consistency
"""
import os
import csv
import uuid
import time
import threading
import requests
import numpy as np
import cv2
import faiss
from collections import defaultdict, deque
from datetime import datetime, timezone

from app.config import NODEJS_BACKEND_URL, NODEJS_AI_API_KEY
from app.face.config import (
    INSIGHTFACE_MODEL, DET_SIZE, EMBEDDINGS_FILE,
    SIMILARITY_THRESHOLD, SIMILARITY_GAP, VOTE_FRAMES, MIN_FACE_SIZE,
    BLUR_THRESHOLD, ATTENDANCE_COOLDOWN_SEC,
)

FACE_LOCK_FRAMES   = 15
STRANGER_ALERT_SEC = 300
REPORT_DIR         = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                        os.path.abspath(__file__)))), "reports")


class FaceRecognizer:
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        # Feature 7: GPU auto-detect
        import onnxruntime as ort
        from insightface.app import FaceAnalysis
        available = ort.get_available_providers()
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if "CUDAExecutionProvider" in available else ["CPUExecutionProvider"]
        print(f"[Face] InsightFace using: {providers[0]}")
        self.app = FaceAnalysis(name=INSIGHTFACE_MODEL, providers=providers)
        self.app.prepare(ctx_id=0, det_size=DET_SIZE)

        self.db_names       = []
        self.db_embeddings  = None
        self.index          = None
        self.neg_embeddings = None      # Feature 1: negative gallery
        self.load_embeddings()

        self.vote_buffer      = defaultdict(lambda: deque(maxlen=VOTE_FRAMES))
        self.track_boxes      = {}
        self._next_track_id   = 0
        self.attendance_log   = {}      # name → last datetime
        self.visitor_log      = {}      # track_id → first_seen
        self.events           = []

        # Feature 2: face lock
        self._face_lock        = {}     # track_id → {name, sim, frames_left}

        # Feature 6: stranger alert
        self._stranger_first   = {}     # track_id → first_seen timestamp
        self._stranger_alerted = set()

        os.makedirs(REPORT_DIR, exist_ok=True)

    # ── Embeddings ────────────────────────────────────────────────────────────

    def load_embeddings(self):
        try:
            with np.load(EMBEDDINGS_FILE, allow_pickle=True) as db:
                self.db_names      = db["names"].tolist()
                self.db_embeddings = db["embeddings"].astype("float32")
                # Feature 1: load negative gallery if present
                if "neg_embeddings" in db:
                    self.neg_embeddings = db["neg_embeddings"].astype("float32")
                    print(f"[Face] Negative gallery: {len(self.neg_embeddings)} embeddings")
                else:
                    self.neg_embeddings = None
            self._build_index()
            print(f"[Face] Loaded {len(set(self.db_names))} person(s): {list(set(self.db_names))}")
        except FileNotFoundError:
            print("[Face] No embeddings — run enroll first")

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

    # ── Feature 3: CLAHE low-light enhancement ────────────────────────────────

    @staticmethod
    def _clahe(img: np.ndarray) -> np.ndarray:
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        cl = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(l)
        return cv2.cvtColor(cv2.merge([cl, a, b]), cv2.COLOR_LAB2BGR)

    # ── Quality ───────────────────────────────────────────────────────────────

    def _quality_ok(self, img, face) -> bool:
        x1, y1, x2, y2 = map(int, face.bbox)
        if (x2-x1) < MIN_FACE_SIZE or (y2-y1) < MIN_FACE_SIZE:
            return False
        crop = img[max(0,y1):y2, max(0,x1):x2]
        if crop.size == 0:
            return False
        # Upscale small faces before blur check
        if crop.shape[0] < 112 or crop.shape[1] < 112:
            crop = cv2.resize(crop, (112, 112), interpolation=cv2.INTER_CUBIC)
        blur = cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
        return blur >= BLUR_THRESHOLD

    # ── Tracker ───────────────────────────────────────────────────────────────

    def _iou(self, a, b) -> float:
        ax1,ay1,ax2,ay2 = a
        bx1,by1,bx2,by2 = b
        ix1,iy1 = max(ax1,bx1), max(ay1,by1)
        ix2,iy2 = min(ax2,bx2), min(ay2,by2)
        inter = max(0,ix2-ix1)*max(0,iy2-iy1)
        union = (ax2-ax1)*(ay2-ay1)+(bx2-bx1)*(by2-by1)-inter
        return inter/union if union > 0 else 0

    def _assign_track(self, bbox) -> int:
        best_id, best_iou = None, 0.3
        for tid, tbox in self.track_boxes.items():
            s = self._iou(bbox, tbox)
            if s > best_iou:
                best_iou, best_id = s, tid
        if best_id is None:
            best_id = self._next_track_id
            self._next_track_id += 1
        self.track_boxes[best_id] = bbox
        return best_id

    # ── Feature 1: Recognition with negative gallery ──────────────────────────

    def _recognize(self, emb):
        if self.index is None:
            return "Unknown", 0.0
        emb32 = emb.astype("float32").reshape(1, -1)
        faiss.normalize_L2(emb32)
        # Negative gallery check
        if self.neg_embeddings is not None:
            neg_sims = self.neg_embeddings @ emb32[0]
            if neg_sims.max() > SIMILARITY_THRESHOLD:
                return "Unknown", float(neg_sims.max())
        k = min(len(self.db_names), 5)
        sims, idxs = self.index.search(emb32, k)
        best: dict[str, float] = {}
        for sim, idx in zip(sims[0], idxs[0]):
            name = self.db_names[int(idx)]
            if name not in best or sim > best[name]:
                best[name] = float(sim)
        sorted_names = sorted(best, key=best.get, reverse=True)
        top_name = sorted_names[0]
        top_sim  = best[top_name]
        # Gap check: top-1 vs top-2 must differ by >= SIMILARITY_GAP
        if len(sorted_names) >= 2:
            gap = top_sim - best[sorted_names[1]]
            if gap < SIMILARITY_GAP:
                return "Unknown", top_sim
        if top_sim >= SIMILARITY_THRESHOLD:
            return top_name, top_sim
        return "Unknown", top_sim

    # ── Feature 8: Node.js attendance POST ───────────────────────────────────

    def _post_to_nodejs(self, name: str, camera_id: str, sim: float):
        try:
            payload = {
                "eventId":    str(uuid.uuid4()),
                "cameraId":   camera_id or "cam6",
                "employeeId": name,
                "eventType":  "FACE_RECOGNIZED",
                "confidence": round(float(sim), 4),
                "timestamp":  datetime.now(timezone.utc).isoformat(),
            }
            resp = requests.post(
                f"{NODEJS_BACKEND_URL}/api/attendance/ai-event",
                json=payload,
                headers={"x-ai-service-key": NODEJS_AI_API_KEY},
                timeout=5,
            )
            data = resp.json()
            if data.get("processed"):
                print(f"[Attendance] {name} marked {data['attendanceAction']} (session={data['sessionId'][:8]}...)")
            else:
                print(f"[Attendance] {name} skipped — {data.get('reason')}")
        except Exception as e:
            print(f"[Attendance] Node.js POST failed for {name}: {e}")

    # ── Feature 5: Attendance CSV export ─────────────────────────────────────

    def _save_attendance_csv(self, name: str, sim: float, dt: datetime):
        try:
            today    = dt.strftime("%Y-%m-%d")
            csv_path = os.path.join(REPORT_DIR, f"attendance_{today}.csv")
            exists   = os.path.exists(csv_path)
            with open(csv_path, "a", newline="") as f:
                w = csv.writer(f)
                if not exists:
                    w.writerow(["name", "time", "similarity", "date"])
                w.writerow([name, dt.strftime("%H:%M:%S"), round(sim, 3), today])
        except Exception as e:
            print(f"[Face] CSV save error: {e}")

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log_event(self, name, track_id, sim, camera_id: str = ""):
        now = datetime.now()
        if name == "Unknown":
            if track_id not in self.visitor_log:
                self.visitor_log[track_id] = now
                self.events.append({"type": "visitor", "name": "Unknown", "track_id": track_id, "sim": round(sim, 3), "timestamp": now.isoformat()})
        else:
            last = self.attendance_log.get(name)
            if last is None or (now - last).seconds >= ATTENDANCE_COOLDOWN_SEC:
                self.attendance_log[name] = now
                self.events.append({"type": "employee", "name": name, "track_id": track_id, "sim": round(sim, 3), "timestamp": now.isoformat()})
                # Feature 5: CSV
                threading.Thread(target=self._save_attendance_csv, args=(name, sim, now), daemon=True).start()
                # Feature 8: Node.js
                threading.Thread(target=self._post_to_nodejs, args=(name, camera_id, sim), daemon=True).start()

    # ── Feature 6: Stranger alert ─────────────────────────────────────────────

    def _check_stranger(self, track_id: int, name: str, camera_id: str):
        now = time.time()
        if name != "Unknown":
            self._stranger_first.pop(track_id, None)
            self._stranger_alerted.discard(track_id)
            return None
        if track_id not in self._stranger_first:
            self._stranger_first[track_id] = now
            return None
        duration = now - self._stranger_first[track_id]
        if duration >= STRANGER_ALERT_SEC and track_id not in self._stranger_alerted:
            self._stranger_alerted.add(track_id)
            alert = {
                "type":         "stranger_alert",
                "track_id":     track_id,
                "camera_id":    camera_id,
                "duration_sec": int(duration),
                "timestamp":    datetime.now().isoformat(),
                "message":      f"Unknown person on {camera_id} for {int(duration//60)}m {int(duration%60)}s",
            }
            self.events.append(alert)
            print(f"[STRANGER ALERT] {alert['message']}")
            return alert
        return None

    # ── Process frame (DEPRECATED — not called by PersonPipeline) ──────────────
    # PersonPipeline._run_face() directly calls fr.app.get() and fr._recognize().
    # This method is kept only for standalone/debug use (e.g. Face_Detection/run.py).
    def process_frame(self, frame: np.ndarray, camera_id: str = "", tracked_persons: list = None):
        # Feature 3: CLAHE for low light
        gray_mean  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean()
        proc_frame = self._clahe(frame) if gray_mean < 80 else frame

        faces   = self.app.get(proc_frame)
        results = []

        # Feature 4: collect all candidates first, then pick best per frame
        face_candidates = []
        for face in faces:
            x1, y1, x2, y2 = map(int, face.bbox)
            if not self._quality_ok(proc_frame, face):
                continue
            track_id = self._assign_track((x1, y1, x2, y2))
            if track_id in self._face_lock:
                lock = self._face_lock[track_id]
                raw_name, sim = lock["name"], lock["sim"]
            else:
                raw_name, sim = self._recognize(face.normed_embedding)
            face_candidates.append((face, track_id, raw_name, sim))

        # Feature 4: only highest-confidence named face wins
        named = [(fc, tid, nm, sm) for fc, tid, nm, sm in face_candidates if nm != "Unknown"]
        best_tid = max(named, key=lambda x: x[3])[1] if named else None

        for face, track_id, raw_name, sim in face_candidates:
            x1, y1, x2, y2 = map(int, face.bbox)

            # Feature 2: face lock
            if track_id in self._face_lock:
                lock = self._face_lock[track_id]
                if track_id != best_tid and lock["name"] != "Unknown":
                    del self._face_lock[track_id]
                else:
                    lock["frames_left"] -= 1
                    if lock["frames_left"] > 0:
                        confirmed = lock["name"]
                        sim       = lock["sim"]
                        color     = (0, 210, 0)
                        label     = f"{confirmed} ({sim:.2f})"
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(frame, label, (x1, y1-8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                        results.append({"track_id": track_id, "name": confirmed, "sim": round(sim, 3),
                                        "bbox": [x1, y1, x2, y2], "confirmed": True, "locked": True})
                        continue
                    else:
                        del self._face_lock[track_id]

            # Feature 4: demote non-best to Unknown
            if raw_name != "Unknown" and track_id != best_tid:
                raw_name = "Unknown"

            self.vote_buffer[track_id].append(raw_name)
            votes = self.vote_buffer[track_id]

            if len(votes) >= VOTE_FRAMES:
                name_votes = [v for v in votes if v != "Unknown"]
                if len(name_votes) >= VOTE_FRAMES - 1 and sim >= SIMILARITY_THRESHOLD:
                    confirmed = max(set(name_votes), key=name_votes.count)
                    self._face_lock[track_id] = {"name": confirmed, "sim": sim, "frames_left": FACE_LOCK_FRAMES}
                else:
                    confirmed = None
            else:
                confirmed = None

            # Feature 6: stranger alert
            self._check_stranger(track_id, confirmed or "Unknown", camera_id)

            if confirmed:
                self._log_event(confirmed, track_id, sim, camera_id)

                # Feature 9: Re-ID anchor
                if confirmed != "Unknown" and tracked_persons:
                    best_gid, best_iou = None, 0.1
                    for tp in tracked_persons:
                        score = self._iou((x1, y1, x2, y2), tp["bbox"])
                        if score > best_iou:
                            best_iou = score
                            best_gid = tp["global_id"]
                    if best_gid is not None:
                        from app.reid.name_anchor import name_anchor
                        name_anchor.set_name(best_gid, confirmed, confidence=sim, camera_id=camera_id)

                color = (0, 210, 0)
                label = f"{confirmed} ({sim:.2f})"
            else:
                color, label = (200, 200, 0), "..."

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, label, (x1, y1-8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

            results.append({
                "track_id":  track_id,
                "name":      confirmed or "voting",
                "sim":       round(sim, 3),
                "bbox":      [x1, y1, x2, y2],
                "confirmed": confirmed is not None,
                "locked":    False,
            })

        # Feature 9: draw anchored names on tracked persons (even without face)
        if tracked_persons:
            from app.reid.name_anchor import name_anchor
            for tp in tracked_persons:
                gid  = tp.get("global_id")
                bbox = tp.get("bbox")
                if gid is None or bbox is None:
                    continue
                anchored = name_anchor.get_name(gid)
                if anchored and anchored != "Unknown":
                    name_anchor.touch(gid, camera_id)
                    x1, y1, x2, y2 = map(int, bbox)
                    label = f"{anchored}"
                    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
                    cv2.rectangle(frame, (x1, y1-th-10), (x1+tw+8, y1), (0, 180, 0), -1)
                    cv2.putText(frame, label, (x1+4, y1-6), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

        return frame, results

    # ── Helpers ───────────────────────────────────────────────────────────────

    def get_attendance_report(self, date: str = None) -> list:
        today    = date or datetime.now().strftime("%Y-%m-%d")
        csv_path = os.path.join(REPORT_DIR, f"attendance_{today}.csv")
        if os.path.exists(csv_path):
            with open(csv_path, "r") as f:
                return list(csv.DictReader(f))
        return []

    def get_stranger_alerts(self) -> list:
        return [e for e in self.events if e.get("type") == "stranger_alert"]

    def reset_session(self):
        self.vote_buffer.clear()
        self.track_boxes.clear()
        self.visitor_log.clear()
        self.events.clear()
        self._face_lock.clear()
        self._stranger_first.clear()
        self._stranger_alerted.clear()
        self._next_track_id = 0
