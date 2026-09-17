"""
app/face/recognizer.py — Face Recognition Engine for smartstore
"""
import uuid
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
    SIMILARITY_THRESHOLD, VOTE_FRAMES, MIN_FACE_SIZE,
    BLUR_THRESHOLD, ATTENDANCE_COOLDOWN_SEC,
)


class FaceRecognizer:
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        from insightface.app import FaceAnalysis
        self.app = FaceAnalysis(name=INSIGHTFACE_MODEL, providers=["CPUExecutionProvider"])
        self.app.prepare(ctx_id=0, det_size=DET_SIZE)

        self.db_names      = []
        self.db_embeddings = None
        self.index         = None
        self.load_embeddings()

        self.vote_buffer    = defaultdict(lambda: deque(maxlen=VOTE_FRAMES))
        self.track_boxes    = {}
        self._next_track_id = 0
        self.attendance_log = {}   # name → last datetime
        self.visitor_log    = {}   # track_id → first_seen
        self.events         = []

    # ── Embeddings ────────────────────────────────────────────────────────────

    def load_embeddings(self):
        try:
            with np.load(EMBEDDINGS_FILE, allow_pickle=True) as db:
                self.db_names      = db["names"].tolist()
                self.db_embeddings = db["embeddings"].astype("float32")
            self._build_index()
            print(f"[Face] Loaded {len(self.db_names)} person(s): {self.db_names}")
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

    # ── Quality ───────────────────────────────────────────────────────────────

    def _quality_ok(self, img, face) -> bool:
        x1, y1, x2, y2 = map(int, face.bbox)
        if (x2-x1) < MIN_FACE_SIZE or (y2-y1) < MIN_FACE_SIZE:
            return False
        crop = img[max(0,y1):y2, max(0,x1):x2]
        if crop.size == 0:
            return False
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

    # ── Recognition ───────────────────────────────────────────────────────────

    def _recognize(self, emb):
        if self.index is None:
            return "Unknown", 0.0
        emb32 = emb.astype("float32").reshape(1,-1)
        faiss.normalize_L2(emb32)
        k = min(len(self.db_names), 5)
        sims, idxs = self.index.search(emb32, k)
        best: dict[str, float] = {}
        for sim, idx in zip(sims[0], idxs[0]):
            name = self.db_names[int(idx)]
            if name not in best or sim > best[name]:
                best[name] = float(sim)
        top_name = max(best, key=best.get)
        top_sim  = best[top_name]
        # Hard threshold — sirf tab naam do jab clearly match ho
        if top_sim >= SIMILARITY_THRESHOLD:
            return top_name, top_sim
        return "Unknown", top_sim

    # ── Logging ───────────────────────────────────────────────────────────────

    def _post_to_nodejs(self, name: str, camera_id: str, sim: float):
        """Send attendance event to Node.js backend (runs in background thread)."""
        try:
            payload = {
                "eventId":    str(uuid.uuid4()),
                "cameraId":   camera_id or "CAM-001",
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

    def _log_event(self, name, track_id, sim, camera_id: str = ""):
        now = datetime.now()
        if name == "Unknown":
            if track_id not in self.visitor_log:
                self.visitor_log[track_id] = now
                self.events.append({"type":"visitor","name":"Unknown","track_id":track_id,"sim":round(sim,3),"timestamp":now.isoformat()})
        else:
            last = self.attendance_log.get(name)
            if last is None or (now-last).seconds >= ATTENDANCE_COOLDOWN_SEC:
                self.attendance_log[name] = now
                self.events.append({"type":"employee","name":name,"track_id":track_id,"sim":round(sim,3),"timestamp":now.isoformat()})
                # Fire-and-forget POST to Node.js backend
                threading.Thread(
                    target=self._post_to_nodejs,
                    args=(name, camera_id, sim),
                    daemon=True,
                ).start()

    # ── Process frame ─────────────────────────────────────────────────────────

    def process_frame(self, frame: np.ndarray, camera_id: str = "", tracked_persons: list = None):
        """
        Run detection + recognition on a frame.
        tracked_persons: list of {global_id, bbox} from analytics_service Re-ID
        """
        faces   = self.app.get(frame)
        results = []

        for face in faces:
            x1,y1,x2,y2 = map(int, face.bbox)
            if not self._quality_ok(frame, face):
                continue

            track_id        = self._assign_track((x1,y1,x2,y2))
            raw_name, sim   = self._recognize(face.normed_embedding)

            # Sirf confirmed naam vote buffer mein daalo
            self.vote_buffer[track_id].append(raw_name)
            votes     = self.vote_buffer[track_id]

            # Majority vote — aur minimum sim bhi check karo
            if len(votes) >= VOTE_FRAMES:
                name_votes = [v for v in votes if v != "Unknown"]
                if len(name_votes) >= VOTE_FRAMES - 1 and sim >= SIMILARITY_THRESHOLD:
                    confirmed = max(set(name_votes), key=name_votes.count)
                else:
                    confirmed = None
            else:
                confirmed = None

            if confirmed:
                self._log_event(confirmed, track_id, sim, camera_id)

                # ── Anchor confirmed name to global_id via Re-ID ──────────────
                if confirmed != "Unknown" and tracked_persons:
                    # Find which global_id bbox overlaps with this face bbox
                    best_gid, best_iou = None, 0.1
                    for tp in tracked_persons:
                        score = self._iou((x1,y1,x2,y2), tp["bbox"])
                        if score > best_iou:
                            best_iou = score
                            best_gid = tp["global_id"]
                    if best_gid is not None:
                        from app.reid.name_anchor import name_anchor
                        name_anchor.set_name(best_gid, confirmed, confidence=sim, camera_id=camera_id)

                color = (0,210,0) if confirmed != "Unknown" else (0,0,220)
                label = f"{confirmed} ({sim:.2f})"
            else:
                color, label = (200,200,0), "..."

            cv2.rectangle(frame, (x1,y1), (x2,y2), color, 2)
            cv2.putText(frame, label, (x1, y1-8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

            results.append({
                "track_id":  track_id,
                "name":      confirmed or "voting",
                "sim":       round(sim,3),
                "bbox":      [x1,y1,x2,y2],
                "confirmed": confirmed is not None,
            })

        # ── Draw anchored names on tracked persons (even without face) ────────
        if tracked_persons:
            from app.reid.name_anchor import name_anchor
            for tp in tracked_persons:
                gid  = tp.get("global_id")
                bbox = tp.get("bbox")
                if gid is None or bbox is None:
                    continue
                anchored_name = name_anchor.get_name(gid)
                if anchored_name and anchored_name != "Unknown":
                    name_anchor.touch(gid, camera_id)
                    x1,y1,x2,y2 = map(int, bbox)
                    # Draw name banner on top of person box
                    label = f"{anchored_name}"
                    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
                    cv2.rectangle(frame, (x1, y1-th-10), (x1+tw+8, y1), (0,180,0), -1)
                    cv2.putText(frame, label, (x1+4, y1-6), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255,255,255), 2)

        return frame, results

    def reset_session(self):
        self.vote_buffer.clear()
        self.track_boxes.clear()
        self.visitor_log.clear()
        self.events.clear()
        self._next_track_id = 0
