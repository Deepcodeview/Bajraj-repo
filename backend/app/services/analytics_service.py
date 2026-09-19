import cv2
import os
import time
import logging
import threading
import queue
import numpy as np
from typing import Callable, Optional

from ultralytics import YOLO
import supervision as sv

from app.config import (
    PERSON_MODEL_PATH, PERSON_CLASS_ID,
    ANNOTATION_SKIP_FRAMES,
    DATASET_COLLECT, DATASET_DIR, DATASET_SAVE_EVERY_N,
    SHELF_MODEL_PATH, SHELF_EMPTY_MODEL_PATH, OUT_OF_STOCK_MODEL_PATH, PHONE_MODEL_PATH,
    STREAM_JPEG_QUALITY, STREAM_RESIZE_WIDTH,
    STREAM_PUSHER_FPS, STREAM_PUSHER_QUALITY, STREAM_PUSHER_WIDTH,
    CROWD_THRESH, QUEUE_ZONE_THRESH, LOITERING_THRESH_SEC, LOITERING_EXEMPT_CAMERAS, OUTDOOR_CAMERAS, PERSON_CAMERAS,
    VEHICLE_MODEL_PATH,
    SHOW_CONFIDENCE, HEATMAP_ALPHA, DEVICE,
)
from app.models.tracker import Tracker
from app.models.shelf import ShelfDetector, draw_shelf_legend, draw_shelf_overlay
from app.utils.video_utils import draw_heatmap_overlay, draw_stats_hud
from app.reid.global_registry import global_registry
from app.reid.name_anchor import name_anchor
from app.services.person_pipeline import PersonPipeline

log = logging.getLogger(__name__)

REID_EVERY_N = 10

# ── Active pipelines registry — camera_id → PersonPipeline (for hot-reload) ──
_active_pipelines: dict = {}

# ── Shared model singletons — loaded once, reused by all 8 camera threads ─────
_person_model      = None
_person_model_lock = threading.Lock()

_vehicle_model      = None
_vehicle_model_lock = threading.Lock()

_phone_model      = None
_phone_model_lock = threading.Lock()

_oos_model      = None
_oos_model_lock = threading.Lock()


def _get_person_model() -> YOLO:
    global _person_model
    if _person_model is None:
        with _person_model_lock:
            if _person_model is None:
                log.info("[singleton] Loading shared YOLO person model...")
                _person_model = YOLO(PERSON_MODEL_PATH)
                log.info("[singleton] Person model ready.")
    return _person_model


def _get_vehicle_model() -> YOLO:
    global _vehicle_model
    if _vehicle_model is None:
        with _vehicle_model_lock:
            if _vehicle_model is None:
                log.info("[singleton] Loading shared vehicle model...")
                _vehicle_model = YOLO(VEHICLE_MODEL_PATH)
                log.info("[singleton] Vehicle model ready.")
    return _vehicle_model


def _get_phone_model():
    global _phone_model
    if _phone_model is None:
        with _phone_model_lock:
            if _phone_model is None and os.path.exists(PHONE_MODEL_PATH):
                log.info("[singleton] Loading shared phone model...")
                _phone_model = YOLO(PHONE_MODEL_PATH)
                log.info("[singleton] Phone model ready.")
    return _phone_model


def _get_oos_model():
    global _oos_model
    if _oos_model is None:
        with _oos_model_lock:
            if _oos_model is None and os.path.exists(OUT_OF_STOCK_MODEL_PATH):
                log.info("[singleton] Loading shared out_of_stock model...")
                _oos_model = YOLO(OUT_OF_STOCK_MODEL_PATH)
                log.info("[singleton] OOS model ready.")
    return _oos_model


# ── Background threads ────────────────────────────────────────────────────────

def _dataset_writer_thread(save_queue: queue.Queue):
    while True:
        item = save_queue.get()
        if item is None:
            break
        try:
            img_path, lbl_path, frame, labels = item
            cv2.imwrite(img_path, frame)
            if labels:
                with open(lbl_path, "w") as lf:
                    lf.write(labels)
        except Exception:
            pass
        save_queue.task_done()


def _stream_pusher_thread(job_id: str, annotated_holder: list, stop_event: threading.Event):
    """
    Independent 30-FPS stream pusher.
    Reads latest annotated frame from holder, encodes JPEG, pushes to WebSocket subscribers.
    Completely decoupled from AI — runs at constant FPS regardless of AI speed.
    """
    interval = 1.0 / STREAM_PUSHER_FPS
    from app.utils.streamer import frame_streamer
    while not stop_event.is_set():
        t0 = time.time()
        frame = annotated_holder[0]
        if frame is not None:
            try:
                h, w = frame.shape[:2]
                if w > STREAM_PUSHER_WIDTH:
                    scale = STREAM_PUSHER_WIDTH / w
                    frame = cv2.resize(frame, (STREAM_PUSHER_WIDTH, int(h * scale)),
                                       interpolation=cv2.INTER_LINEAR)
                _, buf = cv2.imencode(".jpg", frame,
                                      [cv2.IMWRITE_JPEG_QUALITY, STREAM_PUSHER_QUALITY])
                frame_streamer.put(job_id, buf.tobytes())
            except Exception:
                pass
        elapsed = time.time() - t0
        sleep_t = interval - elapsed
        if sleep_t > 0:
            stop_event.wait(timeout=sleep_t)


def _main_stream_reader_thread(rtsp_url: str, frame_holder: list, stop_event: threading.Event):
    STALE_TIMEOUT = 10.0
    MAX_FAILURES  = 30
    retry_delay   = 2.0

    def _connect():
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            "rtsp_transport;tcp|buffer_size;8000000"
            "|max_delay;1000000|stimeout;35000000"
            "|reorder_queue_size;500|loglevel;quiet"
        )
        c = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        c.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return c

    cap = _connect()
    failures = 0
    last_frame_time = time.time()

    while not stop_event.is_set():
        ret, frame = False, None
        try:
            if cap and cap.isOpened():
                ret, frame = cap.read()
        except Exception:
            pass

        if ret and frame is not None:
            frame_holder[0] = frame
            last_frame_time = time.time()
            failures = 0
            retry_delay = 2.0
        else:
            failures += 1
            if time.time() - last_frame_time > STALE_TIMEOUT:
                frame_holder[0] = None
            if failures >= MAX_FAILURES:
                log.warning(f"[main_reader] reconnecting in {retry_delay}s...")
                try:
                    if cap:
                        cap.release()
                except Exception:
                    pass
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60.0)
                cap = _connect()
                failures = 0
                last_frame_time = time.time()
            else:
                time.sleep(0.2)
    try:
        if cap:
            cap.release()
    except Exception:
        pass


def _frame_reader_thread(
    cap,
    frame_queue: queue.Queue,
    stop_event: threading.Event,
    job_id: str,
    is_rtsp: bool,
    video_path: str,
    annotated_holder: Optional[list] = None,
):
    """Dedicated thread: reads frames from cap and puts into frame_queue."""
    last_frame_time = time.time()
    reconnect_cooldown = time.time() + 15.0

    while not stop_event.is_set():
        ret, frame = False, None
        try:
            if cap and cap.isOpened():
                ret, frame = cap.read()
        except Exception as e:
            log.warning(f"[{job_id}] cap.read error: {e}")
            ret, frame = False, None

        if not ret or frame is None:
            if is_rtsp:
                now = time.time()
                # Reconnect ONLY after 20s of total frame starvation
                if (now - last_frame_time > 20.0) and (now > reconnect_cooldown):
                    log.warning(f"[{job_id}] Frame reader timeout (>20s without frames). Reconnecting to RTSP: {video_path}")
                    try:
                        if cap:
                            cap.release()
                    except Exception:
                        pass
                    time.sleep(1.0)
                    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                        "rtsp_transport;tcp|buffer_size;4000000"
                        "|max_delay;1000000|stimeout;35000000"
                        "|reorder_queue_size;500|loglevel;quiet"
                    )
                    try:
                        cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    except Exception as ce:
                        log.error(f"[{job_id}] VideoCapture reconnect failed: {ce}")
                    last_frame_time = time.time()
                    reconnect_cooldown = time.time() + 15.0
                else:
                    time.sleep(0.04)
                continue
            else:
                frame_queue.put(None)  # signal EOF
                break

        last_frame_time = time.time()

        # Seed annotated_holder immediately so stream pusher sends real frames to client
        if annotated_holder is not None and annotated_holder[0] is None:
            annotated_holder[0] = frame

        # Drop stale frames — keep queue fresh (only latest frame matters)
        if frame_queue.full():
            try:
                frame_queue.get_nowait()
            except Exception:
                pass
        try:
            frame_queue.put_nowait(frame)
        except Exception:
            pass

    try:
        if cap:
            cap.release()
    except Exception:
        pass

def process_video(
    video_path: str,
    job_id: str = "unknown",
    progress_cb: Optional[Callable[[int], None]] = None,
    zones_data: Optional[list] = None,
    entry_zone_data: Optional[list] = None,
    exit_zone_data: Optional[list] = None,
    entry_line_ratio: float = None,
    exit_line_ratio: float = None,
    entry_direction: str = "down",
    exit_direction: str = "up",
    conf: float = 0.35,
    mode: str = "indoor",
    dataset_rtsp_url: str = "",
    camera_id: str = "unknown",
    camera_name: str = "",
    stop_event: Optional[threading.Event] = None,
) -> dict:

    is_rtsp   = isinstance(video_path, str) and video_path.startswith("rtsp://")
    is_indoor = mode == "indoor"
    is_vehicle = mode == "vehicle"
    stop_event = stop_event or threading.Event()

    # ── Open stream ───────────────────────────────────────────────────────────
    cap = None
    if is_rtsp:
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            "rtsp_transport;tcp|buffer_size;4000000"
            "|max_delay;1000000|stimeout;35000000"
            "|reorder_queue_size;500|loglevel;quiet"
        )
        log.info(f"[{job_id}] Opening RTSP stream: {video_path}")
        cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            log.warning(f"[{job_id}] First RTSP open failed, retrying once...")
            time.sleep(1.0)
            cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        log.info(f"[{job_id}] RTSP stream initialized (isOpened={cap.isOpened()}). Loading YOLO...")

    # ── Load models ───────────────────────────────────────────────────────────
    person_model = _get_person_model()

    is_outdoor = camera_id in OUTDOOR_CAMERAS
    vehicle_model = _get_vehicle_model() if is_outdoor else None
    log.info(f"[{job_id}] Vehicle model {'ready' if vehicle_model else 'skipped'}")

    phone_model = _get_phone_model() if camera_id not in OUTDOOR_CAMERAS else None
    if phone_model:
        log.info(f"[{job_id}] Phone model ready.")

    shelf_detector = None
    shelf_result   = {"status": "NO SHELF DETECTED", "occupied": 0, "available": 0,
                      "occupancy": 0.0, "empty_zones": 0, "reduced_zones": 0}
    if camera_id == "cam3":
        oos = _get_oos_model()
        if oos:
            shelf_detector = ShelfDetector(None, None, oos)
            log.info(f"[{job_id}] Shelf detector ready: out_of_stock.pt")
        else:
            log.warning(f"[{job_id}] out_of_stock.pt not found")

    # ── Open cap (non-RTSP) ───────────────────────────────────────────────────
    _first_frame = None
    if is_rtsp:
        log.info(f"[{job_id}] Waiting for initial RTSP keyframe (up to 10s)...")
        deadline = time.time() + 10.0
        while time.time() < deadline and not stop_event.is_set():
            ret, _f = cap.read()
            if ret and _f is not None:
                _first_frame = _f
                log.info(f"[{job_id}] Initial RTSP frame ready ({_f.shape[1]}x{_f.shape[0]})")
                break
            time.sleep(0.1)
    else:
        try:
            source = int(video_path)
        except ValueError:
            source = video_path
        cap = cv2.VideoCapture(source)

    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video source: {video_path}")

    width        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps          = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    log.info(f"[{job_id}] {width}x{height} @ {fps:.1f}fps")

    # ── Background threads ────────────────────────────────────────────────────
    save_queue   = queue.Queue(maxsize=10)
    frame_queue  = queue.Queue(maxsize=2)   # small — always process latest frame
    main_stop    = stop_event
    frame_holder = [None]
    annotated_holder = [_first_frame]  # seed with first frame for instant stream

    threading.Thread(target=_dataset_writer_thread, args=(save_queue,), daemon=True).start()

    # Frame reader starts AFTER cap is fully opened and drained
    threading.Thread(
        target=_frame_reader_thread,
        args=(cap, frame_queue, main_stop, job_id, is_rtsp, video_path, annotated_holder),
        daemon=True,
        name=f"frame-reader-{camera_id}",
    ).start()
    log.info(f"[{job_id}] Frame reader thread started.")

    # Independent stream pusher — 30 FPS, decoupled from AI
    threading.Thread(
        target=_stream_pusher_thread,
        args=(job_id, annotated_holder, main_stop),
        daemon=True,
        name=f"stream-pusher-{camera_id}",
    ).start()
    log.info(f"[{job_id}] Stream pusher thread started.")

    # Main stream reader: indoor cameras — high-res frame for face recognition
    use_main_stream = bool(dataset_rtsp_url and is_indoor)
    if use_main_stream:
        threading.Thread(
            target=_main_stream_reader_thread,
            args=(dataset_rtsp_url, frame_holder, main_stop),
            daemon=True,
        ).start()
        log.info(f"[{job_id}] Main stream reader started for face recognition on {camera_id}.")

    # ── Per-camera state ──────────────────────────────────────────────────────
    tracker  = Tracker()

    # ── PersonPipeline — owns the full diagram flow ───────────────────────────
    # CAMERA → PERSON DETECTION → PERSON TRACKING → PERSON ID
    # → FACE DETECTION + BODY TRACKING → ZONE ENGINE → Dwell/Journey/Heatmap
    pipeline = PersonPipeline(camera_id=camera_id, camera_name=camera_name)
    _active_pipelines[camera_id] = pipeline

    frame_count   = 0
    last_progress = -1
    video_start   = time.time()
    entries       = 0
    exits         = 0
    prev_inside   = 0
    zone_counts_total: dict = {}

    try:
        while not main_stop.is_set():
            try:
                frame = frame_queue.get(timeout=2.0)
            except queue.Empty:
                if not is_rtsp:
                    break   # video file ended
                continue    # RTSP — wait for next frame

            if frame is None:
                break  # EOF signal from reader thread

            frame_count += 1

            # Stream raw frame immediately — browser sees video instantly
            annotated_holder[0] = frame

            if frame_count % ANNOTATION_SKIP_FRAMES != 0:
                continue

            if total_frames > 0:
                pct = int((frame_count / total_frames) * 100)
                if pct // 5 != last_progress // 5:
                    last_progress = pct
                    if progress_cb:
                        progress_cb(pct)

            # ── OUTDOOR mode (cam1, cam4, cam5): Vehicle detection ──────────
            if is_outdoor:
                VEHICLE_CLASSES = [2, 3, 5, 7]  # car, motorcycle, bus, truck
                VEHICLE_LABELS  = {2: "Car", 3: "Moto", 5: "Bus", 7: "Truck"}
                out_results = vehicle_model(
                    frame, conf=conf, classes=VEHICLE_CLASSES,
                    verbose=False, device=DEVICE, iou=0.35
                )[0]
                out_count = len(out_results.boxes)
                annotated = frame.copy()
                for box in out_results.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cls_id = int(box.cls[0])
                    cf     = float(box.conf[0])
                    lbl    = VEHICLE_LABELS.get(cls_id, "Vehicle")
                    if SHOW_CONFIDENCE:
                        lbl = f"{lbl} {cf:.2f}"
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 200, 255), 2)
                    (tw, th), _ = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                    cv2.rectangle(annotated, (x1, y1 - th - 8), (x1 + tw + 4, y1), (0, 200, 255), -1)
                    cv2.putText(annotated, lbl, (x1 + 2, y1 - 4),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)
                cv2.putText(annotated, f"Vehicles: {out_count}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 255), 2)
                annotated_holder[0] = annotated
                if frame_count % 15 == 0 and progress_cb:
                    _cb(progress_cb, last_progress, out_count, out_count, 0, 0,
                        shelf_result, mode, 0, 0, {}, {}, False, False, False, 0,
                        camera_id=camera_id)
                continue

            # ── VEHICLE mode (cam5): vehicle detection only ───────────────────
            if is_vehicle:
                VEHICLE_CLASSES = [2, 3, 5, 7]  # car, motorcycle, bus, truck
                v_results  = vehicle_model(
                    frame, conf=conf, classes=VEHICLE_CLASSES,
                    verbose=False, device=DEVICE
                )[0]
                v_count = len(v_results.boxes)
                # Draw boxes
                for box in v_results.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cls_id = int(box.cls[0])
                    label  = {2: "Car", 3: "Moto", 5: "Bus", 7: "Truck"}.get(cls_id, "Vehicle")
                    cf     = float(box.conf[0])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 255), 2)
                    cv2.putText(frame, f"{label} {cf:.2f}", (x1, y1 - 6),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 2)
                cv2.putText(frame, f"Vehicles: {v_count}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 255), 2)
                # Dataset collection
                if DATASET_COLLECT and frame_count % DATASET_SAVE_EVERY_N == 0:
                    try:
                        from app.routers.camera import is_dataset_enabled
                        if is_dataset_enabled(camera_id) and v_count > 0:
                            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                            if cv2.Laplacian(gray, cv2.CV_64F).var() >= 50:
                                import datetime
                                sf    = cv2.resize(frame, (1280, 720))
                                today = datetime.datetime.now().strftime("%Y-%m-%d")
                                ts    = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:20]
                                idir  = os.path.join(DATASET_DIR, camera_id, today, "images")
                                ldir  = os.path.join(DATASET_DIR, camera_id, today, "labels")
                                os.makedirs(idir, exist_ok=True)
                                os.makedirs(ldir, exist_ok=True)
                                h_s, w_s = sf.shape[:2]
                                sx, sy   = w_s / frame.shape[1], h_s / frame.shape[0]
                                yolo_lbl = ""
                                for box in v_results.boxes:
                                    x1,y1,x2,y2 = map(float, box.xyxy[0])
                                    cls_id = int(box.cls[0])
                                    yolo_lbl += (
                                        f"{cls_id} {((x1+x2)/2*sx)/w_s:.6f} "
                                        f"{((y1+y2)/2*sy)/h_s:.6f} "
                                        f"{((x2-x1)*sx)/w_s:.6f} "
                                        f"{((y2-y1)*sy)/h_s:.6f}\n"
                                    )
                                fname = f"{camera_id}_{ts}"
                                if not save_queue.full():
                                    save_queue.put_nowait((
                                        os.path.join(idir, f"{fname}.jpg"),
                                        os.path.join(ldir, f"{fname}.txt"),
                                        sf, yolo_lbl,
                                    ))
                    except Exception as e:
                        log.error(f"[{job_id}] Vehicle dataset save error: {e}")
                annotated_holder[0] = frame
                if frame_count % 15 == 0 and progress_cb:
                    _cb(progress_cb, last_progress, v_count, v_count, 0, 0,
                        shelf_result, mode, 0, 0, {}, {}, False, False, False, 0)
                continue

            # ── STEP 1: PERSON DETECTION (YOLO) ──────────────────────────────
            detect_conf = 0.40 if camera_id in PERSON_CAMERAS else conf
            results     = person_model(
                frame, conf=detect_conf, classes=[PERSON_CLASS_ID],
                verbose=False, device=DEVICE, iou=0.35
            )[0]
            detections = sv.Detections.from_ultralytics(results)

            # Extra NMS pass — removes any remaining overlapping boxes
            if len(detections) > 1:
                detections = detections.with_nms(threshold=0.35)

            # ── STEP 2: PERSON TRACKING (ByteTrack) ──────────────────────────
            tracked = tracker.update(detections)

            # ── STEPS 3-7: Full pipeline via PersonPipeline ───────────────────
            # PersonPipeline handles:
            #   PERSON ID (global_id via Re-ID)
            #   FACE DETECTION (InsightFace, every N frames)
            #   BODY TRACKING (name_anchor when face unavailable)
            #   ZONE ENGINE (entry/exit/dwell/journey/heatmap)
            #   ALERT ENGINE (loitering/crowd/queue/shelf)
            run_reid = (frame_count % REID_EVERY_N == 0)
            # Pass main-stream high-res frame for face recognition if available
            face_frame = frame_holder[0] if use_main_stream and frame_holder[0] is not None else None
            live     = pipeline.process_frame(frame, tracked, run_reid=run_reid, face_frame=face_frame)

            currently_inside    = live["currently_inside"]
            zone_counts_current = live["zone_current"]
            dwell_avg           = live["dwell_avg_sec"]
            dwell_max           = live["dwell_max_sec"]
            heatmap             = live["heatmap"]

            for z, cnt in zone_counts_current.items():
                zone_counts_total[z] = zone_counts_total.get(z, 0) + cnt

            # Entry / Exit
            if currently_inside > prev_inside:
                entries += currently_inside - prev_inside
            elif currently_inside < prev_inside:
                exits += prev_inside - currently_inside
            prev_inside = currently_inside

            queue_alert = any(v >= QUEUE_ZONE_THRESH for v in zone_counts_current.values())
            crowd_alert = currently_inside >= CROWD_THRESH

            # ── Loitering detection ───────────────────────────────────────────
            loitering_ids = ([] if camera_id in LOITERING_EXEMPT_CAMERAS else [
                ps.global_id for ps in pipeline._persons.values()
                if (time.time() - ps.dwell_start) >= LOITERING_THRESH_SEC
                and not ps.is_staff
                and ps.name is None
            ])

            # ── Shelf detection (CAM-3 only) ──────────────────────────────────
            if shelf_detector is not None and frame_count % 5 == 0:
                try:
                    shelf_result = shelf_detector.detect(frame)
                    from app.services.alert_engine import alert_engine as _ae
                    _ae.check_shelf_empty(camera_id, shelf_result["status"], pipeline.store_id)
                except Exception as e:
                    log.warning(f"[{job_id}] Shelf error: {e}")

            # ── Annotate: heatmap overlay + shelf boxes + HUD ─────────────────
            annotated = draw_heatmap_overlay(frame.copy(), heatmap, alpha=HEATMAP_ALPHA) \
                        if heatmap is not None else frame.copy()

            # ── Loitering highlight ───────────────────────────────────────────
            for gid in loitering_ids:
                ps = pipeline._persons.get(gid)
                if ps and ps.bbox:
                    x1, y1, x2, y2 = ps.bbox
                    dwell = int(time.time() - ps.dwell_start)
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)
                    cv2.putText(annotated, f"LOITERING {dwell}s",
                                (x1, y1 - 20), cv2.FONT_HERSHEY_SIMPLEX,
                                0.6, (0, 0, 255), 2, cv2.LINE_AA)

            # ── Crowd / Queue alert banner ────────────────────────────────────
            if crowd_alert:
                cv2.rectangle(annotated, (0, 0), (annotated.shape[1], 36), (0, 0, 180), -1)
                cv2.putText(annotated, f"CROWD ALERT: {currently_inside} persons",
                            (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            elif queue_alert:
                top_zone = max(zone_counts_current, key=zone_counts_current.get)
                cv2.rectangle(annotated, (0, 0), (annotated.shape[1], 36), (0, 100, 200), -1)
                cv2.putText(annotated, f"QUEUE ALERT: {top_zone} ({zone_counts_current[top_zone]})",
                            (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

            if shelf_detector is not None and shelf_result.get("method") == "model":
                try:
                    draw_shelf_overlay(annotated, shelf_result)
                except Exception as e:
                    log.warning(f"[{job_id}] Shelf annotation error: {e}")

            annotated = draw_stats_hud(annotated, {
                "currently_inside":    currently_inside,
                "total_unique_people": tracker.total_unique_people,
                "entries": entries, "exits": exits,
                "dwell_avg_sec": dwell_avg,
                "queue_alert": queue_alert,
            })

            # ── Phone detection overlay ───────────────────────────────────────
            phone_alert = False
            phone_count = 0
            if phone_model is not None:
                try:
                    ph_res   = phone_model(annotated, conf=0.4, verbose=False, device=DEVICE)[0]
                    cam_gids = global_registry.get_active_on_camera(camera_id)
                    # All tracked persons (not just identified employees)
                    emp_boxes = {}
                    if tracked.tracker_id is not None:
                        for box, tid in zip(tracked.xyxy, tracked.tracker_id):
                            gid = cam_gids.get(int(tid), int(tid))
                            emp_boxes[gid] = list(map(int, box))

                    detected_emp = set()
                    for ph_box in ph_res.boxes.xyxy:
                        px1, py1, px2, py2 = map(int, ph_box)
                        for gid, (ex1, ey1, ex2, ey2) in emp_boxes.items():
                            if px1 < ex2 and px2 > ex1 and py1 < ey2 and py2 > ey1:
                                detected_emp.add(gid)
                                phone_alert = True
                                phone_count += 1
                                from app.services.alert_engine import alert_engine as _ae
                                _ae.check_phone_usage(gid, camera_id, pipeline.store_id)
                                cv2.rectangle(annotated, (px1, py1), (px2, py2), (0,0,255), 2)
                                lbl = f"{name_anchor.get_name(gid)}: Using Phone"
                                cv2.rectangle(annotated, (px1, py1-24),
                                              (px1+len(lbl)*11, py1), (0,0,255), -1)
                                cv2.putText(annotated, lbl, (px1+4, py1-6),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,255,255), 2)
                                break
                    for gid in emp_boxes:
                        if gid in detected_emp:
                            name_anchor.phone_start(gid)
                        else:
                            name_anchor.phone_end(gid)
                except Exception as _pe:
                    log.debug(f"[{job_id}] Phone detection skipped: {_pe}")

            # ── Stream frame ──────────────────────────────────────────────────
            annotated_holder[0] = annotated

            # ── Dataset collection ────────────────────────────────────────────
            if DATASET_COLLECT and frame_count % DATASET_SAVE_EVERY_N == 0:
                try:
                    from app.routers.camera import is_dataset_enabled
                    if is_dataset_enabled(camera_id) and \
                       tracked.tracker_id is not None and len(tracked) > 0:
                        hres    = frame_holder[0] if use_main_stream \
                                  and frame_holder[0] is not None else frame
                        gray    = cv2.cvtColor(hres, cv2.COLOR_BGR2GRAY)
                        if cv2.Laplacian(gray, cv2.CV_64F).var() >= 50 and gray.std() >= 10:
                            import datetime
                            sf    = cv2.resize(hres, (1280, 720))
                            today = datetime.datetime.now().strftime("%Y-%m-%d")
                            ts    = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:20]
                            fname = f"{camera_id}_{ts}"
                            idir  = os.path.join(DATASET_DIR, camera_id, today, "images")
                            ldir  = os.path.join(DATASET_DIR, camera_id, today, "labels")
                            os.makedirs(idir, exist_ok=True)
                            os.makedirs(ldir, exist_ok=True)
                            h_s, w_s = sf.shape[:2]
                            sx, sy   = w_s / hres.shape[1], h_s / hres.shape[0]
                            yolo_lbl = ""
                            for box in tracked.xyxy:
                                x1,y1,x2,y2 = box
                                yolo_lbl += (
                                    f"0 {((x1+x2)/2*sx)/w_s:.6f} "
                                    f"{((y1+y2)/2*sy)/h_s:.6f} "
                                    f"{((x2-x1)*sx)/w_s:.6f} "
                                    f"{((y2-y1)*sy)/h_s:.6f}\n"
                                )
                            if not save_queue.full():
                                save_queue.put_nowait((
                                    os.path.join(idir, f"{fname}.jpg"),
                                    os.path.join(ldir, f"{fname}.txt"),
                                    sf, yolo_lbl,
                                ))
                except Exception as e:
                    log.error(f"[{job_id}] Dataset save error: {e}")

            # ── Footfall snapshot → SQLite every 30 frames ────────────────────
            if frame_count % 30 == 0:
                _save_footfall(camera_id, entries, exits, currently_inside,
                               tracker.total_unique_people)

            # ── Progress callback ─────────────────────────────────────────────
            if frame_count % 15 == 0 and progress_cb:
                _cb(progress_cb, last_progress,
                    tracker.total_unique_people, currently_inside,
                    entries, exits, shelf_result, mode,
                    dwell_avg, dwell_max,
                    zone_counts_current, zone_counts_total,
                    queue_alert, crowd_alert, phone_alert, phone_count,
                    camera_id=camera_id)

    finally:
        main_stop.set()
        save_queue.put(None)
        _active_pipelines.pop(camera_id, None)
        # cap released by frame_reader_thread

    processing_time = round(time.time() - video_start, 1)
    log.info(f"[{job_id}] Done. {frame_count} frames in {processing_time}s")
    if progress_cb:
        progress_cb(100)

    return {
        "total_unique_people":    tracker.total_unique_people,
        "currently_inside":       0,
        "entries":                entries,
        "exits":                  exits,
        "shelf_status":           "N/A",
        "mode":                   mode,
        "dwell_avg_sec":          0,
        "dwell_max_sec":          0,
        "zone_totals":            dict(zone_counts_total),
        "total_frames_processed": frame_count,
        "processing_time_sec":    processing_time,
        "video_meta": {
            "width": width, "height": height,
            "fps": round(fps, 2), "total_frames": total_frames,
        },
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _stream(job_id: str, frame: np.ndarray):
    try:
        if STREAM_RESIZE_WIDTH > 0 and frame.shape[1] > STREAM_RESIZE_WIDTH:
            h = int(frame.shape[0] * STREAM_RESIZE_WIDTH / frame.shape[1])
            frame = cv2.resize(frame, (STREAM_RESIZE_WIDTH, h), interpolation=cv2.INTER_LINEAR)
        _, jpeg_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, STREAM_JPEG_QUALITY])
        from app.utils.streamer import frame_streamer
        frame_streamer.put(job_id, jpeg_buf.tobytes())
    except Exception:
        pass


def _cb(progress_cb, last_progress, total_unique, currently_inside,
        entries, exits, shelf_result, mode, dwell_avg, dwell_max,
        zone_current, zone_totals, queue_alert, crowd_alert,
        phone_alert, phone_count, camera_id=""):
    try:
        live = {
            "total_unique_people": total_unique,
            "currently_inside":    currently_inside,
            "entries":             entries,
            "exits":               exits,
            "shelf_status":        shelf_result["status"],
            "shelf_occupancy":     shelf_result["occupancy"],
            "shelf_occupied":      shelf_result["occupied"],
            "shelf_available":     shelf_result["available"],
            "shelf_empty_zones":   shelf_result.get("empty_zones", 0),
            "shelf_reduced_zones": shelf_result.get("reduced_zones", 0),
            "shelf_out_of_stock":  shelf_result.get("out_of_stock", 0),
            "shelf_label_counts":  shelf_result.get("label_counts", {}),
            "mode":                mode,
            "dwell_avg_sec":       dwell_avg,
            "dwell_max_sec":       dwell_max,
            "zone_current":        dict(zone_current),
            "zone_totals":         dict(zone_totals),
            "queue_alert":         queue_alert,
            "crowd_alert":         crowd_alert,
            "phone_alert":         phone_alert,
            "phone_count":         phone_count,
        }
        progress_cb(last_progress if last_progress != -1 else 0, live)
        try:
            from app.routers.camera import update_retail_state
            update_retail_state(camera_id, live)
        except Exception:
            pass
    except Exception:
        pass


def _assign_zone(cx: float, cy: float) -> str:
    row = "Top" if cy < 0.33 else "Mid" if cy < 0.66 else "Bottom"
    col = "Left" if cx < 0.33 else "Center" if cx < 0.66 else "Right"
    return f"{row}-{col}"


def _save_footfall(camera_id: str, entries: int, exits: int,
                   currently_inside: int, total_unique: int):
    """Persist footfall snapshot to PostgreSQL via Node.js."""
    import threading
    def _run():
        try:
            from datetime import datetime, timezone, timedelta
            from app.services.pg_sync import sync_footfall
            IST = timezone(timedelta(hours=5, minutes=30))
            today = datetime.now(IST).strftime("%Y-%m-%d")
            sync_footfall(camera_id, "store_1", today, entries, exits, currently_inside, total_unique)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()
