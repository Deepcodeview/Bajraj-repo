"""
core/config.py — Central config for Face Recognition system
"""
import os

BASE_DIR         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR         = os.path.join(BASE_DIR, "data")           # enrollment images
EMBEDDINGS_FILE  = os.path.join(BASE_DIR, "models", "embeddings.npz")
LOG_DIR          = os.path.join(BASE_DIR, "logs")
STATIC_DIR       = os.path.join(BASE_DIR, "static")

# InsightFace model
INSIGHTFACE_MODEL = "buffalo_l"
DET_SIZE          = (1280, 1280)

# Recognition thresholds
SIMILARITY_THRESHOLD = 0.55
VOTE_FRAMES          = 3
MIN_FACE_SIZE        = 15
BLUR_THRESHOLD       = 3.0

# Camera identity — must match camera_code in the DB for this camera
CAMERA_ID = os.getenv("CAMERA_ID", "cam6")

# Attendance
ATTENDANCE_COOLDOWN_SEC = 60   # same person log once per minute

# Tracking
MAX_LOST_FRAMES     = 30      # frames before lost track is removed
MIN_HITS_TO_CONFIRM = 3       # frames before NEW → ACTIVE
IOU_MATCH_THRESHOLD = 0.3     # IoU threshold for track-detection association

# Ensure dirs exist
for d in [DATA_DIR, os.path.dirname(EMBEDDINGS_FILE), LOG_DIR, STATIC_DIR]:
    os.makedirs(d, exist_ok=True)
