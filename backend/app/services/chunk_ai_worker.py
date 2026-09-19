"""
services/chunk_ai_worker.py — Background Zone & AI Worker for Video Chunks
==========================================================================
Decoupled Architecture:
- Consumes completed 1-2 minute video chunks from an isolated queue.
- Samples video frames at 3-5 FPS (saves 75-85% CPU/GPU, prevents server crash/OOM).
- Zone Engine: Evaluates polygon zones & 3x3 grid (dwell time, occupancy, loitering).
- Keyframe Anomaly Detection: Saves alert snapshots ready for GPT-4o / Vision analysis.
- Database Integration: Syncs structured analytics via pg_sync to Node.js.
- Disk Retention: Auto-cleans video chunks older than 24 hours.
"""

import os
import cv2
import time
import queue
import logging
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any

from app.services.analytics_service import _get_person_model
from app.services.pg_sync import sync_alert, sync_footfall

log = logging.getLogger("retail-ai.chunk_worker")

SNAPSHOTS_DIR = Path("outputs/snapshots")
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


class ChunkAIWorker:
    def __init__(
        self,
        sample_fps: int = 4,
        retention_hours: int = 24,
        max_queue_size: int = 100,
    ):
        self.sample_fps = sample_fps
        self.retention_hours = retention_hours
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Camera-specific zone overrides: camera_id -> list of zones
        # Zone format: {"name": "Entrance", "type": "entrance", "points": [[x1, y1], [x2, y2], ...]}
        self._camera_zones: Dict[str, List[dict]] = {}
        self._lock = threading.Lock()

        # In-memory history of recent processed chunk analytics (last 50)
        self.recent_results: List[dict] = []
        self.stats = {
            "worker_status": "idle",
            "queue_depth": 0,
            "total_chunks_processed": 0,
            "total_frames_analyzed": 0,
            "last_processed_chunk": None,
            "last_processing_duration_sec": 0.0,
            "last_error": None,
        }

    def start(self):
        if self._running:
            return
        self._running = True
        self.stats["worker_status"] = "running"
        self._thread = threading.Thread(target=self._worker_loop, name="chunk-ai-worker", daemon=True)
        self._thread.start()
        log.info(f"✅ Chunk AI Worker started (sample_fps={self.sample_fps}, retention={self.retention_hours}h)")

    def stop(self):
        self._running = False
        self._queue.put(None)  # Sentinel to unblock
        self.stats["worker_status"] = "stopped"
        log.info("Chunk AI Worker stopped.")

    def enqueue_chunk(self, chunk_meta: dict):
        """Enqueue a completed chunk for background AI processing."""
        try:
            self._queue.put_nowait(chunk_meta)
            self.stats["queue_depth"] = self._queue.qsize()
            log.info(f"Enqueued chunk for AI analysis: {chunk_meta.get('filename')} (queue depth={self.stats['queue_depth']})")
        except queue.Full:
            log.warning(f"Chunk AI Worker queue full! Dropping oldest item to prevent server freeze.")
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(chunk_meta)
            except Exception:
                pass

    def set_camera_zones(self, camera_id: str, zones: List[dict]):
        with self._lock:
            self._camera_zones[camera_id] = zones
        log.info(f"[{camera_id}] Set {len(zones)} custom zones for chunk AI worker.")

    def get_camera_zones(self, camera_id: str) -> List[dict]:
        with self._lock:
            return self._camera_zones.get(camera_id, [])

    # ── Main Worker Loop: Process Chunks with Total Error Isolation ────────────
    def _worker_loop(self):
        while self._running:
            try:
                item = self._queue.get(timeout=2.0)
            except queue.Empty:
                self._cleanup_old_chunks()
                continue

            if item is None or not self._running:
                break

            self.stats["queue_depth"] = self._queue.qsize()
            chunk_path = item.get("video_path")
            camera_id = item.get("camera_id", "unknown")

            try:
                t0 = time.time()
                analysis = self._process_chunk_video(chunk_path, camera_id, item)
                duration = round(time.time() - t0, 2)

                self.stats["total_chunks_processed"] += 1
                self.stats["last_processing_duration_sec"] = duration
                self.stats["last_processed_chunk"] = item.get("filename")

                # Store recent result in memory
                analysis["processing_time_sec"] = duration
                analysis["chunk_meta"] = item
                with self._lock:
                    self.recent_results.insert(0, analysis)
                    if len(self.recent_results) > 50:
                        self.recent_results.pop()

                log.info(
                    f"[{camera_id}] Processed chunk {item.get('filename')} in {duration}s — "
                    f"People seen: {analysis['unique_persons_count']}, "
                    f"Max concurrent: {analysis['peak_occupancy']}, "
                    f"Alerts: {len(analysis['alerts'])}"
                )

            except Exception as e:
                self.stats["last_error"] = str(e)
                log.error(f"[{camera_id}] Error analyzing chunk {chunk_path}: {e}", exc_info=True)
            finally:
                self._queue.task_done()
                self.stats["queue_depth"] = self._queue.qsize()

    # ── Analyze Video Chunk using Frame Sampling & Zone Logic ─────────────────
    def _process_chunk_video(self, video_path: str, camera_id: str, chunk_meta: dict) -> dict:
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video chunk not found: {video_path}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video file: {video_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Determine sampling step
        sample_step = max(1, int(round(video_fps / self.sample_fps)))

        # Load shared person model
        model = _get_person_model()
        zones = self.get_camera_zones(camera_id)

        frame_idx = 0
        analyzed_frames = 0
        peak_occupancy = 0
        zone_occupancy_counts = {}
        person_tracking = {}  # track_id -> {"first_seen": t, "last_seen": t, "zones": set()}
        alerts = []
        anomaly_snapshots = []

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            if frame_idx % sample_step == 0:
                analyzed_frames += 1
                self.stats["total_frames_analyzed"] += 1
                timestamp_offset = round(frame_idx / video_fps, 1)

                # Run YOLO person detection (class 0 = person)
                results = model.track(
                    frame,
                    persist=True,
                    classes=[0],
                    conf=0.35,
                    verbose=False,
                )

                current_persons_in_frame = 0
                if results and len(results) > 0 and results[0].boxes is not None:
                    boxes = results[0].boxes
                    current_persons_in_frame = len(boxes)

                    for box in boxes:
                        xyxy = box.xyxy[0].cpu().numpy().tolist()
                        x1, y1, x2, y2 = xyxy
                        cx_norm = ((x1 + x2) / 2.0) / width
                        cy_norm = ((y1 + y2) / 2.0) / height

                        # Track ID if available
                        track_id = int(box.id[0].item()) if box.id is not None else None

                        # Match zone
                        matched_zone = self._find_zone_for_point(cx_norm, cy_norm, width, height, zones)
                        zone_occupancy_counts[matched_zone] = zone_occupancy_counts.get(matched_zone, 0) + 1

                        if track_id is not None:
                            if track_id not in person_tracking:
                                person_tracking[track_id] = {
                                    "first_seen": timestamp_offset,
                                    "last_seen": timestamp_offset,
                                    "zones": {matched_zone},
                                }
                            else:
                                person_tracking[track_id]["last_seen"] = timestamp_offset
                                person_tracking[track_id]["zones"].add(matched_zone)

                        # Check for loitering / suspicious dwell (> 45 seconds in a single chunk)
                        if track_id and (timestamp_offset - person_tracking[track_id]["first_seen"] > 45.0):
                            if "loitering" not in person_tracking[track_id]:
                                person_tracking[track_id]["loitering"] = True
                                alert_msg = f"Loitering detected: Person #{track_id} in {matched_zone} for >45s"
                                alerts.append({
                                    "type": "loitering",
                                    "severity": "medium",
                                    "zone": matched_zone,
                                    "message": alert_msg,
                                    "track_id": track_id,
                                    "timestamp_offset": timestamp_offset,
                                })
                                # Capture snapshot
                                snap_name = f"alert_{camera_id}_{chunk_meta.get('timestamp')}_p{track_id}.jpg"
                                snap_path = SNAPSHOTS_DIR / snap_name
                                cv2.imwrite(str(snap_path), frame)
                                anomaly_snapshots.append(str(snap_path))

                if current_persons_in_frame > peak_occupancy:
                    peak_occupancy = current_persons_in_frame

            frame_idx += 1

        cap.release()

        # Dwell time stats across tracked persons in this chunk
        dwell_times = [
            round(p["last_seen"] - p["first_seen"], 1)
            for p in person_tracking.values()
        ]
        avg_dwell = round(sum(dwell_times) / max(len(dwell_times), 1), 1)

        # Build structured GPT/LLM summary
        llm_summary = {
            "camera_id": camera_id,
            "period": f"{chunk_meta.get('duration_sec')}s window at {chunk_meta.get('timestamp')}",
            "unique_people_detected": len(person_tracking),
            "peak_occupancy": peak_occupancy,
            "average_dwell_sec": avg_dwell,
            "zone_activity": zone_occupancy_counts,
            "alerts": alerts,
        }

        # Safe dispatch to Node.js / PostgreSQL sync
        try:
            for alert in alerts:
                sync_alert(
                    alert_type=alert["type"],
                    severity=alert["severity"],
                    camera_id=camera_id,
                    zone=alert["zone"],
                    global_id=alert.get("track_id", 0),
                    message=alert["message"],
                    extra_data={"timestamp_offset": alert.get("timestamp_offset")},
                    store_id="store_main",
                )
            if len(person_tracking) > 0:
                sync_footfall(
                    camera_id=camera_id,
                    store_id="store_main",
                    log_date=time.strftime("%Y-%m-%d"),
                    entries=len(person_tracking),
                    exits=0,
                    currently_inside=peak_occupancy,
                    total_unique=len(person_tracking),
                )
        except Exception as e:
            log.debug(f"pg_sync alert/footfall skipped: {e}")

        return {
            "camera_id": camera_id,
            "total_video_frames": total_frames,
            "analyzed_frames": analyzed_frames,
            "sampling_fps": self.sample_fps,
            "unique_persons_count": len(person_tracking),
            "peak_occupancy": peak_occupancy,
            "avg_dwell_sec": avg_dwell,
            "zone_occupancy": zone_occupancy_counts,
            "alerts": alerts,
            "anomaly_snapshots": anomaly_snapshots,
            "llm_ready_summary": llm_summary,
        }

    # ── Zone Point Matching: Polygon zones or 3x3 Grid ────────────────────────
    def _find_zone_for_point(
        self,
        cx_norm: float,
        cy_norm: float,
        w: int,
        h: int,
        zones: List[dict]
    ) -> str:
        # Check custom polygon zones
        if zones:
            pt = (int(cx_norm * w), int(cy_norm * h))
            for z in zones:
                pts = z.get("points", [])
                if len(pts) >= 3:
                    import numpy as np
                    poly = np.array(pts, dtype=np.int32)
                    if cv2.pointPolygonTest(poly, pt, False) >= 0:
                        return z.get("name", "CustomZone")

        # Fallback 3x3 grid
        row = ["Top", "Mid", "Bottom"][min(int(cy_norm * 3), 2)]
        col = ["Left", "Center", "Right"][min(int(cx_norm * 3), 2)]
        return f"{row}-{col}"

    # ── Auto Disk Cleanup Retention Task ──────────────────────────────────────
    def _cleanup_old_chunks(self):
        """Removes chunks older than retention_hours to protect server disk space."""
        try:
            from app.services.video_chunker import RECORDINGS_DIR
            if not RECORDINGS_DIR.exists():
                return
            cutoff_time = time.time() - (self.retention_hours * 3600)
            for f in RECORDINGS_DIR.glob("**/*.mp4"):
                if f.is_file() and f.stat().st_mtime < cutoff_time:
                    f.unlink()
                    log.info(f"Retention cleaner: deleted expired chunk {f.name}")
        except Exception as e:
            log.debug(f"Retention cleanup error: {e}")


# Singleton
chunk_ai_worker = ChunkAIWorker(sample_fps=4, retention_hours=24)

# Wire video_chunk_manager callback to auto-enqueue chunks into the worker
from app.services.video_chunker import video_chunk_manager
video_chunk_manager.set_on_chunk_callback(chunk_ai_worker.enqueue_chunk)
