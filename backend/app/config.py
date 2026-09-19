"""
config.py — Centralised configuration for the Retail AI backend.
"""

import os

# ── Directories ───────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR  = os.path.join(BASE_DIR, "temp")
OUTPUT_DIR  = os.path.join(BASE_DIR, "outputs")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Model paths ───────────────────────────────
PERSON_MODEL_PATH      = os.path.join(BASE_DIR, "Models", "person_best.pt")
VEHICLE_MODEL_PATH     = os.path.join(BASE_DIR, "yolov8n.pt")  # COCO model for vehicle detection
SHELF_MODEL_PATH       = os.path.join(BASE_DIR, "app", "models", "best.pt")
SHELF_EMPTY_MODEL_PATH  = os.path.join(BASE_DIR, "Models", "empty_best.pt")
OUT_OF_STOCK_MODEL_PATH = os.path.join(BASE_DIR, "Models", "out_of_stock.pt")
PHONE_MODEL_PATH        = os.path.join(BASE_DIR, "Models", "phone_best.pt")

# ── Inference device ────────────────────────
import torch as _torch
DEVICE = "cuda" if _torch.cuda.is_available() else "cpu"

# ── Detection thresholds ─────────────────────
PERSON_CONF     = 0.55
SHELF_CONF      = 0.25
PERSON_CLASS_ID = 0             # COCO class 0 = person

# ── Advanced Detection ───────────────────────
OUTDOOR_CAMERAS       = {"cam1", "cam4"}  # outdoor cameras — vehicle detection only
PERSON_CAMERAS        = {"cam2", "cam3", "cam6", "cam7", "cam8"}  # indoor cameras — full person detection + tracking
LOITERING_THRESH_SEC  = 300  # 5 min — short dwell is normal shopping behaviour
LOITERING_EXEMPT_CAMERAS = {"cam2", "cam3", "cam6", "cam7", "cam8"}  # indoor shopping cameras — no loitering alerts
CROWD_THRESH          = 8
QUEUE_ZONE_THRESH     = 4
SHOW_CONFIDENCE       = True
SHOW_ZONE_LABEL       = True
SHOW_DWELL_TIMER      = True
SHOW_TRAIL            = True
TRAIL_LENGTH          = 30
HEATMAP_ALPHA         = 0.30

# ── Tracking ─────────────────────────────────
IDENTITY_TTL         = 45.0   # seconds to remember a disappeared person
IDENTITY_DIST_THRESH = 400.0  # px distance to re-match a returning person

# ByteTrack tuning (retail CCTV — partial occlusion, slow movement)
BYTETRACK_TRACK_THRESH    = 0.30   # lowered: catch persons at edge of frame
BYTETRACK_MATCH_THRESH    = 0.70   # IoU threshold for matching
BYTETRACK_TRACK_BUFFER    = 60     # frames to keep lost track alive
BYTETRACK_FRAME_RATE      = 15     # match actual RTSP stream FPS
BYTETRACK_MIN_FRAMES      = 2      # lowered: confirm track faster (was 4 — too slow for brief visits)

# ── Footfall line ────────────────────────────
FOOTFALL_LINE_RATIO = 0.65

# ── Video output ─────────────────────────────
SAVE_ANNOTATED_VIDEO   = True
ANNOTATION_SKIP_FRAMES = 1      # process every frame for smooth streaming
STREAM_JPEG_QUALITY    = 65     # used by legacy _stream() calls
STREAM_RESIZE_WIDTH    = 854    # used by legacy _stream() calls

# ── Independent Stream Pusher ─────────────────
STREAM_PUSHER_FPS     = 30    # pusher thread target FPS
STREAM_PUSHER_QUALITY = 40    # JPEG quality for WebSocket stream
STREAM_PUSHER_WIDTH   = 480   # resize width (480p)

# ── Node.js Integration ─────────────────────
NODEJS_BACKEND_URL = os.getenv("NODEJS_BACKEND_URL", "http://localhost:8000")
NODEJS_AI_API_KEY  = os.getenv("NODEJS_AI_API_KEY",  "smart-retail-ai-key-2025")

# ── Dataset Collection ────────────────────────
DATASET_COLLECT      = True
DATASET_CAMERAS      = {"cam6", "cam7", "cam8"}  # indoor cameras — dataset collection enabled
DATASET_DIR          = os.path.join(BASE_DIR, "dataset_collection")
DATASET_SAVE_EVERY_N = 15
DATASET_MIN_CONF     = 0.30
DATASET_MIN_BOX_PX   = 10

for _cam in DATASET_CAMERAS:
    os.makedirs(os.path.join(DATASET_DIR, _cam, "images"), exist_ok=True)
    os.makedirs(os.path.join(DATASET_DIR, _cam, "labels"), exist_ok=True)
os.makedirs(os.path.join(DATASET_DIR, "images"), exist_ok=True)
os.makedirs(os.path.join(DATASET_DIR, "labels"), exist_ok=True)
