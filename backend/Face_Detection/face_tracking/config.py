"""
config.py — Central configuration for Face Tracking System
"""
import os

# ── Input ─────────────────────────────────────────────────────────────────────
SOURCE = 0                        # 0=webcam, "rtsp://...", "video.mp4", 1=USB cam
INPUT_WIDTH  = 1280
INPUT_HEIGHT = 720
TARGET_FPS   = 30

# ── Detection ─────────────────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.5
NMS_IOU_THRESHOLD    = 0.45
MIN_FACE_SIZE        = 20         # px — ignore tiny detections
DETECT_EVERY_N_FRAMES = 2         # run detector every N frames, predict in between

# ── Tracking ──────────────────────────────────────────────────────────────────
MAX_LOST_FRAMES      = 30         # frames before a lost track is removed
MIN_HITS_TO_CONFIRM  = 3          # frames before NEW → ACTIVE
IOU_MATCH_THRESHOLD  = 0.3        # IoU threshold for track-detection association
MAX_TRACK_AGE        = 3600       # seconds — max lifetime of a track

# ── InsightFace (SCRFD detector) ──────────────────────────────────────────────
INSIGHTFACE_MODEL = "buffalo_s"
DET_SIZE          = (640, 640)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR     = os.path.join(BASE_DIR, "models")
LOG_DIR        = os.path.join(BASE_DIR, "logs")
os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(LOG_DIR,    exist_ok=True)

# ── Visualization ─────────────────────────────────────────────────────────────
SHOW_CONFIDENCE  = True
SHOW_TRACK_ID    = True
SHOW_STATUS      = True
BOX_THICKNESS    = 2
FONT_SCALE       = 0.55

# Track status colors (BGR)
COLOR_ACTIVE        = (0, 210, 0)
COLOR_NEW           = (0, 200, 255)
COLOR_LOST          = (0, 100, 255)
COLOR_REMOVED       = (80, 80, 80)
