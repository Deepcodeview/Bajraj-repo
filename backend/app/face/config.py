"""
app/face/config.py — Face Recognition config for smartstore backend
"""
import os

BASE_DIR         = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FACE_DIR         = os.path.join(BASE_DIR, "Face_Detection")

DATA_DIR         = os.path.join(FACE_DIR, "data")
EMBEDDINGS_FILE  = os.path.join(FACE_DIR, "models", "embeddings.npz")

INSIGHTFACE_MODEL    = "buffalo_l"
DET_SIZE             = (1280, 1280)
SIMILARITY_THRESHOLD = 0.55
VOTE_FRAMES          = 3
MIN_FACE_SIZE        = 15
BLUR_THRESHOLD       = 3.0
ATTENDANCE_COOLDOWN_SEC = 60

for d in [DATA_DIR, os.path.dirname(EMBEDDINGS_FILE)]:
    os.makedirs(d, exist_ok=True)
