"""
oakd_camera.py — Camera Integration (OAK-D + HTTP/MJPEG/RTSP)
==============================================================
Supports:
  - OAK-D via DepthAI
  - HTTP MJPEG stream  (e.g. http://localhost:8080/stream)
  - RTSP stream        (e.g. rtsp://...)
  - Local webcam       (e.g. source=0)
"""

import logging
import time
import threading
import numpy as np
from typing import Optional

log = logging.getLogger("retail-ai.camera")

_pipeline = None
_device   = None
_queue    = None
_cap      = None          # cv2.VideoCapture for HTTP/RTSP/webcam
_running  = False
_lock     = threading.Lock()
_last_frame: Optional[np.ndarray] = None
_fps      = 0.0
_source   = "oak-d"       # "oak-d" | stream URL | int
_reconnect_attempts = 0
_MAX_RECONNECT      = 5


# ── HTTP / RTSP / Webcam ──────────────────────────────────────

def start_http_camera(url: str) -> dict:
    """Connect to HTTP MJPEG / RTSP / webcam stream."""
    global _cap, _running, _source, _last_frame, _reconnect_attempts

    import cv2
    stop_camera()

    src = int(url) if url.isdigit() else url

    # RTSP-specific tuning: use TCP transport, set buffer size
    cap = cv2.VideoCapture(src)
    if isinstance(src, str) and src.startswith("rtsp://"):
        # Force TCP transport (more reliable than UDP for H.265)
        # Use environment variable to set RTSP transport before opening
        import os
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|buffer_size;2000000"
        cap.release()
        cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000)

    if not cap.isOpened():
        # Retry once with FFMPEG backend explicitly for RTSP
        if isinstance(src, str) and src.startswith("rtsp://"):
            cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            return {"ok": False, "error": f"Cannot open stream: {url}"}

    _cap                = cap
    _running            = True
    _source             = url
    _reconnect_attempts = 0

    t = threading.Thread(target=_http_frame_grabber, daemon=True)
    t.start()

    w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    log.info(f"✅ HTTP/RTSP camera started: {url}  {w}x{h} @ {fps:.1f}fps")
    return {"ok": True, "message": f"Stream started: {url}", "source": url,
            "resolution": f"{w}x{h}", "fps": round(fps, 1)}


def _http_frame_grabber():
    global _last_frame, _running, _fps, _cap, _reconnect_attempts

    import cv2
    frame_count = 0
    t0 = time.time()

    while _running:
        if _cap is None or not _cap.isOpened():
            # Auto-reconnect for RTSP streams
            if isinstance(_source, str) and _source.startswith("rtsp://") and _reconnect_attempts < _MAX_RECONNECT:
                _reconnect_attempts += 1
                log.warning(f"RTSP stream lost — reconnect attempt {_reconnect_attempts}/{_MAX_RECONNECT}")
                time.sleep(2)
                new_cap = cv2.VideoCapture(_source, cv2.CAP_FFMPEG)
                if new_cap.isOpened():
                    if _cap:
                        _cap.release()
                    _cap = new_cap
                    log.info("RTSP reconnected ✅")
                    continue
            break

        ret, frame = _cap.read()
        if ret and frame is not None:
            with _lock:
                _last_frame = frame
            frame_count += 1
            _reconnect_attempts = 0   # reset on successful read
            elapsed = time.time() - t0
            if elapsed >= 1.0:
                _fps = frame_count / elapsed
                frame_count = 0
                t0 = time.time()
        else:
            time.sleep(0.033)   # ~30fps wait before retry

    _running = False
    log.info("HTTP frame grabber exited")


# ── OAK-D ─────────────────────────────────────────────────────

def start_camera(resolution: str = "720p", fps: int = 30) -> dict:
    """Start OAK-D camera pipeline."""
    global _pipeline, _device, _queue, _running, _last_frame, _source

    try:
        import depthai as dai
    except ImportError:
        return {"ok": False, "error": "depthai not installed"}

    if _running and _device is not None:
        return {"ok": True, "message": "Camera already running", "fps": fps}

    stop_camera()  # ensure clean state after any crash

    try:
        _pipeline = dai.Pipeline()
        cam = _pipeline.create(dai.node.ColorCamera)
        cam.setInterleaved(False)
        cam.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
        cam.setFps(fps)
        cam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_720_P)
        cam.setPreviewSize(640, 480)  # small + stable, avoids black frame issue

        xout = _pipeline.create(dai.node.XLinkOut)
        xout.setStreamName("rgb")
        cam.preview.link(xout.input)

        _device  = dai.Device(_pipeline)
        _queue   = _device.getOutputQueue(name="rgb", maxSize=4, blocking=False)

        # Wait for first real frame before marking as running
        log.info("Waiting for first OAK-D frame…")
        deadline = time.time() + 10
        while time.time() < deadline:
            f = _queue.tryGet()
            if f is not None:
                with _lock:
                    _last_frame = f.getCvFrame()
                break
            time.sleep(0.05)
        else:
            _device.close()
            _device = None
            return {"ok": False, "error": "OAK-D timeout — no frame received in 10s"}

        _running = True
        _source  = "oak-d"

        t = threading.Thread(target=_oakd_frame_grabber, daemon=True)
        t.start()

        log.info(f"✅ OAK-D started: 720p@{fps}fps")
        return {"ok": True, "message": f"OAK-D started: 720p@{fps}fps", "fps": fps}

    except Exception as e:
        _running = False
        log.error(f"OAK-D start failed: {e}")
        return {"ok": False, "error": str(e)}


def _oakd_frame_grabber():
    global _last_frame, _running, _fps

    frame_count = 0
    t0 = time.time()

    while _running and _queue:
        try:
            in_frame = _queue.tryGet()
            if in_frame is not None:
                with _lock:
                    _last_frame = in_frame.getCvFrame()
                frame_count += 1
                elapsed = time.time() - t0
                if elapsed >= 1.0:
                    _fps = frame_count / elapsed
                    frame_count = 0
                    t0 = time.time()
            else:
                time.sleep(0.001)
        except Exception as e:
            log.error(f"OAK-D frame error: {e}")
            time.sleep(0.1)

    _running = False
    log.info("OAK-D frame grabber exited")


# ── Common ────────────────────────────────────────────────────

def stop_camera() -> dict:
    global _device, _cap, _running, _pipeline, _queue, _last_frame

    _running = False
    time.sleep(0.3)

    if _device:
        try:
            _device.close()
        except Exception:
            pass
        _device = None

    if _cap:
        try:
            _cap.release()
        except Exception:
            pass
        _cap = None

    _pipeline = _queue = _last_frame = None
    log.info("Camera stopped")
    return {"ok": True, "message": "Camera stopped"}


def get_frame() -> Optional[np.ndarray]:
    return _last_frame


def get_status() -> dict:
    return {
        "connected":  _running and (_device is not None or (_cap is not None and _cap.isOpened())),
        "fps":        round(_fps, 1),
        "has_frame":  _last_frame is not None,
        "source":     _source,
        "resolution": f"{_last_frame.shape[1]}x{_last_frame.shape[0]}" if _last_frame is not None else None,
    }
