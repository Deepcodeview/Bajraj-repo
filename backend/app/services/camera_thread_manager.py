"""
services/camera_thread_manager.py — Dedicated Thread Pool for Camera Processing

Each camera runs in its own isolated daemon thread.
- Start / stop / restart per camera
- Auto-restart on crash (with backoff)
- Thread health monitoring
- Max 8 concurrent camera threads (one per camera)
"""

import threading
import logging
import time
from typing import Callable, Optional

log = logging.getLogger("CameraThreadManager")

MAX_CAMERAS       = 8
MAX_RESTARTS      = 5
RESTART_BACKOFF   = [2, 4, 8, 16, 32]


class CameraWorker:
    def __init__(self, job_id: str, camera_id: str, target: Callable, args: tuple, kwargs: dict):
        self.job_id    = job_id
        self.camera_id = camera_id
        self._target   = target
        self._args     = args
        self._kwargs   = kwargs

        self._thread:   Optional[threading.Thread] = None
        self._stop_evt  = threading.Event()
        self._restarts  = 0
        self._started_at: Optional[float] = None
        self._crashed_at: Optional[float] = None
        self.status     = "idle"

    def start(self):
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run_with_watchdog,
            name=f"cam-{self.camera_id}-{self.job_id[:8]}",
            daemon=True,
        )
        self._started_at = time.time()
        self.status = "running"
        self._thread.start()
        log.info(f"[{self.camera_id}] Thread started — job={self.job_id[:8]}")

    def stop(self):
        self.status = "stopped"
        self._stop_evt.set()
        log.info(f"[{self.camera_id}] Stop requested — job={self.job_id[:8]}")

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def uptime(self) -> float:
        if self._started_at is None:
            return 0.0
        return round(time.time() - self._started_at, 1)

    def _run_with_watchdog(self):
        while not self._stop_evt.is_set():
            try:
                kwargs = dict(self._kwargs)
                kwargs["stop_event"] = self._stop_evt
                self._target(*self._args, **kwargs)
                self.status = "stopped"
                log.info(f"[{self.camera_id}] Stream ended cleanly.")
                break
            except Exception as e:
                if self._stop_evt.is_set():
                    break
                self._crashed_at = time.time()
                self._restarts  += 1
                log.error(f"[{self.camera_id}] Crashed (attempt {self._restarts}): {e}")

                if self._restarts > MAX_RESTARTS:
                    self.status = "crashed"
                    log.error(f"[{self.camera_id}] Max restarts reached. Giving up.")
                    break

                delay = RESTART_BACKOFF[min(self._restarts - 1, len(RESTART_BACKOFF) - 1)]
                log.info(f"[{self.camera_id}] Restarting in {delay}s...")
                self._stop_evt.wait(timeout=delay)

        self.status = "stopped" if self.status != "crashed" else "crashed"


class CameraThreadManager:
    def __init__(self):
        self._lock    = threading.Lock()
        self._workers: dict = {}

    def start_camera(self, job_id: str, camera_id: str, target: Callable,
                     args: tuple = (), kwargs: dict = None) -> bool:
        kwargs = kwargs or {}
        with self._lock:
            active = sum(1 for w in self._workers.values() if w.is_alive())
            if active >= MAX_CAMERAS:
                log.warning(f"Max camera threads ({MAX_CAMERAS}) reached. Cannot start {camera_id}.")
                return False
            if job_id in self._workers:
                self._workers[job_id].stop()
            worker = CameraWorker(job_id, camera_id, target, args, kwargs)
            self._workers[job_id] = worker

        worker.start()
        return True

    def stop_camera(self, job_id: str):
        with self._lock:
            worker = self._workers.get(job_id)
        if worker:
            worker.stop()

    def stop_all(self):
        with self._lock:
            workers = list(self._workers.values())
        for w in workers:
            w.stop()
        log.info("All camera threads stop-requested.")

    def status(self) -> dict:
        with self._lock:
            return {
                job_id: {
                    "camera_id": w.camera_id,
                    "status":    w.status,
                    "alive":     w.is_alive(),
                    "uptime_sec": w.uptime(),
                    "restarts":  w._restarts,
                }
                for job_id, w in self._workers.items()
            }

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for w in self._workers.values() if w.is_alive())

    def cleanup_dead(self):
        with self._lock:
            dead = [jid for jid, w in self._workers.items() if not w.is_alive()]
            for jid in dead:
                del self._workers[jid]


# Singleton
camera_thread_manager = CameraThreadManager()
