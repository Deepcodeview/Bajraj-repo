"""
services/video_chunker.py — Resilient RTSP Stream Ingest & 1-2 Minute Video Chunker
===================================================================================
Solves:
1. Packet loss & grey frames -> Forces TCP transport for RTSP.
2. Buffer bloat & delay       -> Dedicated grabber thread keeping latest frame (Buffer=1).
3. Continuous recording       -> Rotates video into 1-2 minute MP4 chunks without dropping stream.
4. Asynchronous AI decoupling -> Dispatches completed chunks to background AI queue.
"""

import os
import cv2
import time
import logging
import threading
from pathlib import Path
from typing import Optional, Callable, Dict

log = logging.getLogger("retail-ai.chunker")

# Base directory for storing video chunks
RECORDINGS_DIR = Path("outputs/recordings")


class CameraChunkRecorder:
    """
    Manages continuous video stream ingestion and chunk writing for a single camera.
    """
    def __init__(
        self,
        camera_id: str,
        source: str,
        chunk_duration_sec: int = 120,
        record_fps: int = 15,
        on_chunk_completed: Optional[Callable[[dict], None]] = None,
    ):
        self.camera_id = camera_id
        self.source = int(source) if str(source).isdigit() else str(source)
        self.chunk_duration_sec = max(15, chunk_duration_sec)
        self.record_fps = record_fps
        self.on_chunk_completed = on_chunk_completed

        self._running = False
        self._grab_thread: Optional[threading.Thread] = None
        self._record_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._latest_frame = None
        self._last_frame_time = 0.0

        self.stats = {
            "camera_id": camera_id,
            "status": "idle",
            "chunks_created": 0,
            "current_chunk_path": None,
            "current_chunk_elapsed_sec": 0,
            "fps": 0.0,
            "started_at": None,
            "last_error": None,
        }

        # Ensure output directory exists
        self.camera_dir = RECORDINGS_DIR / self.camera_id
        self.camera_dir.mkdir(parents=True, exist_ok=True)

    def start(self):
        if self._running:
            return
        self._running = True
        self.stats["status"] = "starting"
        self.stats["started_at"] = time.time()

        self._grab_thread = threading.Thread(
            target=self._stream_grabber_loop,
            name=f"grab-{self.camera_id}",
            daemon=True,
        )
        self._record_thread = threading.Thread(
            target=self._chunk_writer_loop,
            name=f"writer-{self.camera_id}",
            daemon=True,
        )

        self._grab_thread.start()
        self._record_thread.start()
        log.info(f"[{self.camera_id}] Video chunker started (chunk_duration={self.chunk_duration_sec}s)")

    def stop(self):
        self._running = False
        self.stats["status"] = "stopped"
        log.info(f"[{self.camera_id}] Video chunker stop requested.")

    def get_latest_frame(self) -> Optional[object]:
        with self._lock:
            if self._latest_frame is not None:
                return self._latest_frame.copy()
        return None

    def is_healthy(self) -> bool:
        return self._running and (time.time() - self._last_frame_time < 8.0)

    # ── Dedicated low-latency grabber loop (Buffer = 1, TCP) ───────────────────
    def _stream_grabber_loop(self):
        is_rtsp = isinstance(self.source, str) and self.source.startswith("rtsp://")

        def _open_cap():
            if is_rtsp:
                # Force TCP transport & fast timeout
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                    "rtsp_transport;tcp|buffer_size;2048000"
                    "|max_delay;500000|stimeout;10000000"
                    "|reorder_queue_size;500|loglevel;quiet"
                )
                c = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
                c.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                return c
            else:
                c = cv2.VideoCapture(self.source)
                c.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                return c

        cap = _open_cap()
        frame_counter = 0
        t0 = time.time()
        reconnect_delay = 2.0

        while self._running:
            if not cap.isOpened():
                self.stats["status"] = "reconnecting"
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, 30.0)
                cap = _open_cap()
                continue

            ret, frame = cap.read()
            if ret and frame is not None:
                reconnect_delay = 2.0
                now = time.time()
                with self._lock:
                    self._latest_frame = frame
                    self._last_frame_time = now

                frame_counter += 1
                elapsed = now - t0
                if elapsed >= 1.0:
                    self.stats["fps"] = round(frame_counter / elapsed, 1)
                    frame_counter = 0
                    t0 = now
                self.stats["status"] = "running"
            else:
                if is_rtsp:
                    log.warning(f"[{self.camera_id}] Read failed on RTSP, reconnecting...")
                    cap.release()
                    time.sleep(1.0)
                    cap = _open_cap()
                else:
                    time.sleep(0.02)

        cap.release()
        log.info(f"[{self.camera_id}] Grabber thread exited.")

    # ── Chunk Writer Loop: writes 1-2 min MP4 segments ─────────────────────────
    def _chunk_writer_loop(self):
        # Wait for first valid frame to determine resolution
        for _ in range(100):
            if not self._running:
                return
            frame = self.get_latest_frame()
            if frame is not None:
                break
            time.sleep(0.1)

        if frame is None:
            self.stats["last_error"] = "No frame received to initialize writer"
            log.error(f"[{self.camera_id}] Writer failed: stream never returned a frame.")
            return

        h, w = frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        frame_interval = 1.0 / self.record_fps

        while self._running:
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            chunk_filename = f"chunk_{self.camera_id}_{timestamp_str}.mp4"
            chunk_filepath = self.camera_dir / chunk_filename

            writer = cv2.VideoWriter(str(chunk_filepath), fourcc, self.record_fps, (w, h))
            if not writer.isOpened():
                log.error(f"[{self.camera_id}] Failed to open VideoWriter for {chunk_filepath}")
                time.sleep(1.0)
                continue

            self.stats["current_chunk_path"] = str(chunk_filepath)
            chunk_start_time = time.time()
            frames_written = 0

            while self._running and (time.time() - chunk_start_time < self.chunk_duration_sec):
                t_frame_start = time.time()
                cur_frame = self.get_latest_frame()
                if cur_frame is not None:
                    # Verify dimensions match
                    if cur_frame.shape[:2] == (h, w):
                        writer.write(cur_frame)
                        frames_written += 1

                self.stats["current_chunk_elapsed_sec"] = int(time.time() - chunk_start_time)
                elapsed = time.time() - t_frame_start
                sleep_sec = frame_interval - elapsed
                if sleep_sec > 0:
                    time.sleep(sleep_sec)

            writer.release()
            duration_actual = round(time.time() - chunk_start_time, 1)

            if frames_written > 10:
                self.stats["chunks_created"] += 1
                chunk_meta = {
                    "camera_id": self.camera_id,
                    "video_path": str(chunk_filepath),
                    "filename": chunk_filename,
                    "timestamp": timestamp_str,
                    "frames_written": frames_written,
                    "duration_sec": duration_actual,
                    "resolution": [w, h],
                    "fps": self.record_fps,
                }
                log.info(f"[{self.camera_id}] Chunk completed: {chunk_filename} ({duration_actual}s, {frames_written} frames)")

                # Notify worker queue
                if self.on_chunk_completed:
                    try:
                        self.on_chunk_completed(chunk_meta)
                    except Exception as e:
                        log.error(f"[{self.camera_id}] on_chunk_completed error: {e}")
            else:
                # Remove empty/corrupted stub file
                try:
                    if chunk_filepath.exists():
                        chunk_filepath.unlink()
                except Exception:
                    pass

        log.info(f"[{self.camera_id}] Chunk writer loop exited.")


class VideoChunkManager:
    """
    Singleton managing multiple active camera chunkers.
    """
    def __init__(self):
        self._recorders: Dict[str, CameraChunkRecorder] = {}
        self._lock = threading.Lock()
        self._on_chunk_callback: Optional[Callable[[dict], None]] = None

    def set_on_chunk_callback(self, cb: Callable[[dict], None]):
        self._on_chunk_callback = cb

    def start_camera(
        self,
        camera_id: str,
        source: str,
        chunk_duration_sec: int = 120,
        record_fps: int = 15,
    ) -> dict:
        with self._lock:
            if camera_id in self._recorders:
                rec = self._recorders[camera_id]
                if rec.stats["status"] == "running":
                    return {"ok": True, "message": "Chunker already running", "camera_id": camera_id}
                rec.stop()

            recorder = CameraChunkRecorder(
                camera_id=camera_id,
                source=source,
                chunk_duration_sec=chunk_duration_sec,
                record_fps=record_fps,
                on_chunk_completed=self._on_chunk_callback,
            )
            self._recorders[camera_id] = recorder
            recorder.start()
            return {"ok": True, "message": "Chunker started", "camera_id": camera_id, "chunk_duration_sec": chunk_duration_sec}

    def stop_camera(self, camera_id: str) -> dict:
        with self._lock:
            rec = self._recorders.get(camera_id)
            if rec:
                rec.stop()
                return {"ok": True, "message": f"Camera {camera_id} chunker stopped"}
            return {"ok": False, "error": f"Camera {camera_id} chunker not found"}

    def stop_all(self):
        with self._lock:
            for rec in self._recorders.values():
                rec.stop()

    def get_latest_frame(self, camera_id: str):
        with self._lock:
            rec = self._recorders.get(camera_id)
        if rec:
            return rec.get_latest_frame()
        return None

    def get_status(self) -> dict:
        with self._lock:
            return {
                cam_id: rec.stats
                for cam_id, rec in self._recorders.items()
            }


video_chunk_manager = VideoChunkManager()
