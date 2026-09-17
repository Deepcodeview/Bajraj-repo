"""
reid/global_registry.py — Cross-camera Global Person ID Registry.
"""

import time
import threading
import numpy as np
from collections import deque
from typing import Optional


class GlobalPersonRegistry:

    def __init__(self, similarity_thresh: float = 0.35, ttl: float = 120.0, history_k: int = 5):
        self.similarity_thresh = similarity_thresh
        self.ttl       = ttl
        self.history_k = history_k
        self._lock     = threading.Lock()
        self._gallery: dict = {}
        self._active_map: dict = {}
        self._next_id: int = 1
        self._last_prune: float = 0.0
        self._prune_interval: float = 30.0

    @staticmethod
    def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))

    def _best_sim(self, embedding: np.ndarray, entry: dict) -> float:
        sims = [self._cosine_sim(embedding, entry["ema"])]
        for h in entry["embeddings"]:
            sims.append(self._cosine_sim(embedding, h))
        return max(sims)

    def _prune_expired(self):
        now = time.time()
        if now - self._last_prune < self._prune_interval:
            return
        self._last_prune = now
        expired = [gid for gid, v in self._gallery.items()
                   if (now - v["last_seen"]) > self.ttl]
        for gid in expired:
            del self._gallery[gid]

    def _find_match(self, embedding: np.ndarray) -> Optional[int]:
        best_gid, best_sim = None, self.similarity_thresh
        for gid, data in self._gallery.items():
            sim = self._best_sim(embedding, data)
            if sim > best_sim:
                best_sim = sim
                best_gid = gid
        return best_gid

    def _update_gallery(self, gid: int, embedding: np.ndarray, camera_id: str):
        entry = self._gallery[gid]
        old_ema = entry["ema"]
        new_ema = 0.8 * old_ema + 0.2 * embedding
        norm = np.linalg.norm(new_ema)
        entry["ema"] = new_ema / (norm + 1e-6)
        entry["embeddings"].append(embedding.copy())
        entry["last_seen"] = time.time()
        entry["camera_id"] = camera_id

    def assign(self, camera_id: str, local_tid: int, embedding: np.ndarray) -> int:
        key = (camera_id, local_tid)
        with self._lock:
            if key in self._active_map:
                gid = self._active_map[key]
                if gid in self._gallery:
                    self._update_gallery(gid, embedding, camera_id)
                return gid
            self._prune_expired()
            matched_gid = self._find_match(embedding)
            if matched_gid is not None:
                gid = matched_gid
                self._update_gallery(gid, embedding, camera_id)
            else:
                gid = self._next_id
                self._next_id += 1
                self._gallery[gid] = {
                    "embeddings": deque([embedding.copy()], maxlen=self.history_k),
                    "ema":        embedding.copy(),
                    "last_seen":  time.time(),
                    "camera_id":  camera_id,
                }
            self._active_map[key] = gid
            return gid

    def release(self, camera_id: str, local_tid: int) -> None:
        key = (camera_id, local_tid)
        with self._lock:
            if key in self._active_map:
                gid = self._active_map.pop(key)
                if gid in self._gallery:
                    self._gallery[gid]["last_seen"] = time.time()

    def get_active_on_camera(self, camera_id: str) -> dict:
        with self._lock:
            return {
                local_tid: gid
                for (cam, local_tid), gid in self._active_map.items()
                if cam == camera_id
            }

    @property
    def total_unique(self) -> int:
        return self._next_id - 1


try:
    from app.face.config import SIMILARITY_THRESHOLD as _REID_THRESH
except Exception:
    _REID_THRESH = 0.40
global_registry = GlobalPersonRegistry(similarity_thresh=_REID_THRESH)
