"""
app/face/config.py — Face Recognition config for smartstore backend
"""
import os

BASE_DIR         = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FACE_DIR         = os.path.join(BASE_DIR, "Face_Detection")

DATA_DIR         = os.path.join(FACE_DIR, "data")
EMBEDDINGS_FILE  = os.path.join(FACE_DIR, "models", "embeddings.npz")

INSIGHTFACE_MODEL    = "buffalo_l"
DET_SIZE             = (1280, 1280)  # larger = better small face detection
SIMILARITY_THRESHOLD = 0.62          # diagram spec: >= 0.62
SIMILARITY_GAP       = 0.06          # diagram spec: top-1 vs top-2 gap >= 0.06
VOTE_FRAMES          = 3
MIN_FACE_SIZE        = 20            # diagram spec: >= 20px
BLUR_THRESHOLD       = 2.0           # diagram spec: >= 2.0
ATTENDANCE_COOLDOWN_SEC = 60

for d in [DATA_DIR, os.path.dirname(EMBEDDINGS_FILE)]:
    os.makedirs(d, exist_ok=True)
