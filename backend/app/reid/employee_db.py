"""
reid/employee_db.py — Persistent Employee Identity Database

Flow:
  Frame → Person detected → Extract face + body embeddings
       → Compare with employee DB (weighted score)
       → If match: assign existing name
       → If no match: Unknown

Identity Score = 0.6 * face_sim + 0.4 * body_sim
Once confirmed, name persists even if face disappears.

Thread-safe singleton.
"""

import time
import threading
import numpy as np
from typing import Optional

# Weights for combined identity score
FACE_WEIGHT   = 0.6
BODY_WEIGHT   = 0.4
FACE_THRESH   = 0.45   # min face similarity to count
BODY_THRESH     = 0.82   # min body similarity to count (high to avoid false matches)
COMBINED_THRESH = 0.50   # min combined score to confirm identity

# How long to remember a person after last seen (seconds)
IDENTITY_TTL  = 7200.0  # 2 hours


class EmployeeProfile:
    """Stores all visual features for one employee."""
    __slots__ = (
        "name", "face_embeddings", "body_embeddings",
        "last_seen", "last_camera", "confidence",
        "face_confirmed", "total_sightings",
    )

    def __init__(self, name: str):
        self.name             = name
        self.face_embeddings: list[np.ndarray] = []   # up to 10 best face embs
        self.body_embeddings: list[np.ndarray] = []   # up to 20 best body embs
        self.last_seen        = time.time()
        self.last_camera      = ""
        self.confidence       = 0.0
        self.face_confirmed   = False
        self.total_sightings  = 0

    def update_face(self, emb: np.ndarray, sim: float):
        """Add high-confidence face embedding."""
        if sim < FACE_THRESH:
            return
        self.face_embeddings.append(emb.copy())
        if len(self.face_embeddings) > 10:
            self.face_embeddings.pop(0)
        self.face_confirmed = True
        self.confidence     = max(self.confidence, sim)

    def update_body(self, emb: np.ndarray, sim: float = 1.0):
        """Add body Re-ID embedding."""
        if np.linalg.norm(emb) < 0.1:
            return
        self.body_embeddings.append(emb.copy())
        if len(self.body_embeddings) > 20:
            self.body_embeddings.pop(0)

    def best_face_sim(self, emb: np.ndarray) -> float:
        """Max cosine similarity against stored face embeddings."""
        if not self.face_embeddings or emb is None:
            return 0.0
        sims = [float(np.dot(emb, f)) for f in self.face_embeddings]
        return max(sims)

    def best_body_sim(self, emb: np.ndarray) -> float:
        """Max cosine similarity against stored body embeddings."""
        if not self.body_embeddings or emb is None:
            return 0.0
        sims = [float(np.dot(emb, b)) for b in self.body_embeddings]
        return max(sims)

    def identity_score(self, face_emb: Optional[np.ndarray],
                       body_emb: Optional[np.ndarray]) -> float:
        """
        Face available hone par hi identify karo.
        Body alone se kabhi identify mat karo — false positives bahut hote hain.
        """
        if face_emb is None:
            return 0.0   # body alone se identify nahi karenge
        face_sim = self.best_face_sim(face_emb)
        return face_sim if face_sim >= FACE_THRESH else 0.0


class EmployeeIdentityDB:
    """
    Persistent employee identity database.
    Matches incoming face+body embeddings against known employees.
    """

    def __init__(self):
        self._lock     = threading.Lock()
        # name → EmployeeProfile
        self._profiles: dict[str, EmployeeProfile] = {}
        # global_id → (name, last_confirmed_time)
        self._id_cache: dict[int, tuple[str, float]] = {}
        self._cache_ttl = 300.0   # 5 min — if same global_id seen, reuse name

    def load_enrolled(self, embeddings_file: str):
        """
        Load face embeddings from enroll.py output (embeddings.npz).
        Called once at startup.
        """
        import os
        if not os.path.exists(embeddings_file):
            return
        try:
            db = np.load(embeddings_file, allow_pickle=True)
            names = db["names"].tolist()
            embs  = db["embeddings"].astype("float32")
            for name, emb in zip(names, embs):
                if name not in self._profiles:
                    self._profiles[name] = EmployeeProfile(name)
                self._profiles[name].face_embeddings.append(emb)
                self._profiles[name].face_confirmed = True
            print(f"[EmployeeDB] Loaded {len(set(names))} employees: {list(set(names))}")
        except Exception as e:
            print(f"[EmployeeDB] Load error: {e}")

    def identify(
        self,
        global_id:  int,
        face_emb:   Optional[np.ndarray] = None,
        body_emb:   Optional[np.ndarray] = None,
        camera_id:  str = "",
    ) -> tuple[str, float]:
        """
        Identify a person by face + body embeddings.
        Returns (name, confidence). name="Unknown" if no match.

        Priority:
        1. global_id cache (same track, already confirmed)
        2. Face + body combined match
        3. Unknown
        """
        with self._lock:
            # 1. Check global_id cache first
            cached = self._id_cache.get(global_id)
            if cached:
                name, ts = cached
                if time.time() - ts < self._cache_ttl:
                    # Update profile last_seen
                    if name in self._profiles:
                        p = self._profiles[name]
                        p.last_seen   = time.time()
                        p.last_camera = camera_id
                        # Update body embedding if available
                        if body_emb is not None:
                            p.update_body(body_emb)
                    return name, self._profiles[name].confidence if name in self._profiles else 0.8

            # 2. Match against all profiles
            best_name  = "Unknown"
            best_score = COMBINED_THRESH

            for name, profile in self._profiles.items():
                score = profile.identity_score(face_emb, body_emb)
                if score > best_score:
                    best_score = score
                    best_name  = name

            if best_name != "Unknown":
                # Update profile
                p = self._profiles[best_name]
                p.last_seen      = time.time()
                p.last_camera    = camera_id
                p.total_sightings += 1
                if face_emb is not None:
                    p.update_face(face_emb, best_score)
                if body_emb is not None:
                    p.update_body(body_emb)

                # Cache this global_id → name
                self._id_cache[global_id] = (best_name, time.time())

            return best_name, round(best_score, 3)

    def confirm_face(self, global_id: int, name: str, face_emb: np.ndarray,
                     sim: float, camera_id: str = ""):
        """
        Called when face recognition confirms a name.
        Updates profile + caches global_id.
        """
        with self._lock:
            if name not in self._profiles:
                self._profiles[name] = EmployeeProfile(name)
            p = self._profiles[name]
            p.update_face(face_emb, sim)
            p.last_seen   = time.time()
            p.last_camera = camera_id
            p.total_sightings += 1
            self._id_cache[global_id] = (name, time.time())

    def update_body(self, global_id: int, body_emb: np.ndarray, camera_id: str = ""):
        """Update body embedding for cached global_id."""
        with self._lock:
            cached = self._id_cache.get(global_id)
            if cached:
                name, ts = cached
                if time.time() - ts < self._cache_ttl and name in self._profiles:
                    self._profiles[name].update_body(body_emb)
                    self._profiles[name].last_seen   = time.time()
                    self._profiles[name].last_camera = camera_id

    def release_track(self, global_id: int):
        """Called when a track disappears — keep cache for re-entry."""
        # Do NOT delete from cache — person may re-appear
        pass

    def get_status(self) -> list:
        """Return all employee profiles for dashboard."""
        with self._lock:
            now = time.time()
            return [
                {
                    "name":           p.name,
                    "face_confirmed": p.face_confirmed,
                    "face_samples":   len(p.face_embeddings),
                    "body_samples":   len(p.body_embeddings),
                    "last_camera":    p.last_camera,
                    "last_seen_sec":  round(now - p.last_seen),
                    "confidence":     round(p.confidence, 3),
                    "sightings":      p.total_sightings,
                }
                for p in self._profiles.values()
            ]

    def reload(self, embeddings_file: str):
        """Reload face embeddings (after re-enrollment)."""
        with self._lock:
            # Keep body embeddings, refresh face embeddings
            for p in self._profiles.values():
                p.face_embeddings.clear()
                p.face_confirmed = False
        self.load_enrolled(embeddings_file)


# Singleton
employee_db = EmployeeIdentityDB()
