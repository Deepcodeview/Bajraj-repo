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
    CROWD_THRESH, QUEUE_ZONE_THRESH, LOITERING_THRESH_SEC, LOITERING_EXEMPT_CAMERAS,
    SHOW_CONFIDENCE, HEATMAP_ALPHA,
)
from app.models.tracker import Tracker
from app.models.shelf import ShelfDetector, draw_shelf_legend, draw_shelf_overlay
from app.utils.video_utils import draw_heatmap_overlay, draw_stats_hud
from app.reid.global_registry import global_registry
from app.reid.name_anchor import name_anchor
from app.services.person_pipeline import PersonPipeline

log = logging.getLogger(__name__)

REID_EVERY_N = 5


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


def _main_stream_reader_thread(rtsp_url: str, frame_holder: list, stop_event: threading.Event):
    STALE_TIMEOUT = 10.0
    MAX_FAILURES  = 30
    retry_delay   = 2.0

    def _connect():
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            "rtsp_transport;tcp|buffer_size;8000000"
            "|max_delay;1000000|stimeout;15000000"
            "|reorder_queue_size;500|loglevel;quiet"
        )
        c = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        c.set(cv2.CAP_PROP_BUFFERSIZE, 10)
        return c

    cap = _connect()
    failures = 0
    last_frame_time = time.time()

    while not stop_event.is_set():
        ret, frame = cap.read()
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
                cap.release()
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60.0)
                cap = _connect()
                failures = 0
                last_frame_time = time.time()
            else:
                time.sleep(0.2)
    cap.release()


def _frame_reader_thread(cap, frame_queue: queue.Queue, stop_event: threading.Event, job_id: str, is_rtsp: bool, video_path: str):
    """Dedicated thread: reads frames from cap and puts into frame_queue."""
    MAX_FAILURES = 10 if is_rtsp else 1
    consecutive_failures = 0

    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret or frame is None:
            if is_rtsp:
                consecutive_failures += 1
                if consecutive_failures >= MAX_FAILURES:
                    log.warning(f"[{job_id}] Frame reader reconnecting...")
                    cap.release()
                    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                        "rtsp_transport;tcp|buffer_size;4000000"
                        "|max_delay;1000000|stimeout;15000000"
                        "|reorder_queue_size;500|loglevel;quiet"
                    )
                    cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    consecutive_failures = 0
                time.sleep(0.05)
                continue
            else:
                frame_queue.put(None)  # signal EOF
                break
        consecutive_failures = 0
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

    cap.release()

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
            "|max_delay;1000000|stimeout;15000000"
            "|reorder_queue_size;500|loglevel;quiet"
        )
        cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 10)
        log.info(f"[{job_id}] RTSP connected. Loading YOLO...")

    # ── Load models ───────────────────────────────────────────────────────────
    log.info(f"[{job_id}] Loading YOLO person model...")
    person_model = YOLO(PERSON_MODEL_PATH)

    vehicle_model = YOLO(VEHICLE_MODEL_PATH) if not is_indoor else None
    log.info(f"[{job_id}] Vehicle model {'loaded' if vehicle_model else 'skipped (indoor)'}")

    phone_model = None
    if os.path.exists(PHONE_MODEL_PATH):
        phone_model = YOLO(PHONE_MODEL_PATH)
        log.info(f"[{job_id}] Phone model loaded.")

    shelf_detector = None
    shelf_result   = {"status": "NO SHELF DETECTED", "occupied": 0, "available": 0,
                      "occupancy": 0.0, "empty_zones": 0, "reduced_zones": 0}
    if camera_id == "cam3":
        slot_m       = YOLO(SHELF_MODEL_PATH)         if os.path.exists(SHELF_MODEL_PATH)         else None
        empty_m      = YOLO(SHELF_EMPTY_MODEL_PATH)   if os.path.exists(SHELF_EMPTY_MODEL_PATH)   else None
        out_of_stock = YOLO(OUT_OF_STOCK_MODEL_PATH)  if os.path.exists(OUT_OF_STOCK_MODEL_PATH)  else None
        if slot_m or empty_m or out_of_stock:
            shelf_detector = ShelfDetector(slot_m, empty_m, out_of_stock)
            log.info(f"[{job_id}] Shelf models loaded (out_of_stock={'yes' if out_of_stock else 'no'}).")

    # ── Open cap (non-RTSP) ───────────────────────────────────────────────────
    if is_rtsp:
        log.info(f"[{job_id}] Draining stale RTSP frames...")
        drained = 0
        for _ in range(60):
            ret, _f = cap.read()
            drained += 1
            if ret and _f is not None:
                import numpy as _np
                if _f.mean() > 5.0 and _np.std(_f) > 5.0:
                    log.info(f"[{job_id}] Valid keyframe found after {drained} drain frames.")
                    break
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

    threading.Thread(target=_dataset_writer_thread, args=(save_queue,), daemon=True).start()

    # Frame reader starts AFTER cap is fully opened and drained
    threading.Thread(
        target=_frame_reader_thread,
        args=(cap, frame_queue, main_stop, job_id, is_rtsp, video_path),
        daemon=True,
        name=f"frame-reader-{camera_id}",
    ).start()
    log.info(f"[{job_id}] Frame reader thread started.")

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

            if frame_count % ANNOTATION_SKIP_FRAMES != 0:
                continue

            if total_frames > 0:
                pct = int((frame_count / total_frames) * 100)
                if pct // 5 != last_progress // 5:
                    last_progress = pct
                    if progress_cb:
                        progress_cb(pct)

            # ── OUTDOOR mode: Vehicle detection only ─────────────────────────
            if not is_indoor and not is_vehicle:
                VEHICLE_CLASSES = [2, 3, 5, 7]  # car, motorcycle, bus, truck
                VEHICLE_LABELS  = {2: "Car", 3: "Moto", 5: "Bus", 7: "Truck"}
                out_results = vehicle_model(
                    frame, conf=conf, classes=VEHICLE_CLASSES,
                    verbose=False, device="mps", iou=0.35
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
                _stream(job_id, annotated)
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
                    verbose=False, device="mps"
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
                _stream(job_id, frame)
                if frame_count % 15 == 0 and progress_cb:
                    _cb(progress_cb, last_progress, v_count, v_count, 0, 0,
                        shelf_result, mode, 0, 0, {}, {}, False, False, False, 0)
                continue
                try:
                    from app.face.recognizer import FaceRecognizer
                    fr = FaceRecognizer.get()
                    if fr.index is not None:
                        frame, _ = fr.process_frame(frame)
                except Exception:
                    pass

                # Dataset collection for outdoor cameras (cam7 etc.)
                if DATASET_COLLECT and frame_count % DATASET_SAVE_EVERY_N == 0:
                    try:
                        from app.routers.camera import is_dataset_enabled
                        if is_dataset_enabled(camera_id):
                            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                            if cv2.Laplacian(gray, cv2.CV_64F).var() >= 50 and gray.std() >= 10:
                                import datetime
                                # Run YOLO to get person bboxes for labels
                                out_results  = person_model(
                                    frame, conf=conf, classes=[PERSON_CLASS_ID],
                                    verbose=False, device="mps"
                                )[0]
                                out_tracked  = sv.Detections.from_ultralytics(out_results)
                                sf    = cv2.resize(frame, (1280, 720))
                                today = datetime.datetime.now().strftime("%Y-%m-%d")
                                ts    = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:20]
                                idir  = os.path.join(DATASET_DIR, camera_id, today, "images")
                                ldir  = os.path.join(DATASET_DIR, camera_id, today, "labels")
                                os.makedirs(idir, exist_ok=True)
                                os.makedirs(ldir, exist_ok=True)
                                fname  = f"{camera_id}_{ts}"
                                h_s, w_s = sf.shape[:2]
                                sx, sy   = w_s / frame.shape[1], h_s / frame.shape[0]
                                yolo_lbl = ""
                                if out_tracked.xyxy is not None:
                                    for box in out_tracked.xyxy:
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
                        log.error(f"[{job_id}] Outdoor dataset save error: {e}")

                _stream(job_id, frame)
                if frame_count % 15 == 0 and progress_cb:
                    _cb(progress_cb, last_progress, 0, 0, 0, 0, shelf_result,
                        mode, 0, 0, {}, {}, False, False, False, 0)
                continue

            # ── STEP 1: PERSON DETECTION (YOLO) ──────────────────────────────
            detect_conf = 0.55 if camera_id in ("cam2", "cam3", "cam6", "cam7", "cam8") else conf
            results     = person_model(
                frame, conf=detect_conf, classes=[PERSON_CLASS_ID],
                verbose=False, device="mps", iou=0.35
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
                    ph_res   = phone_model(annotated, conf=0.4, verbose=False, device="mps")[0]
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
            _stream(job_id, annotated)

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
