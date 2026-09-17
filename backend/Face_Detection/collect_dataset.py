"""
collect_dataset.py — Auto dataset collection from camera/video/RTSP
Usage:
  python collect_dataset.py --name "ch 701" --count 100
  python collect_dataset.py --name "ch 701" --count 100 --cam 1
  python collect_dataset.py --name "ch 701" --count 100 --source rtsp://192.168.1.100/stream
  python collect_dataset.py --name "ch 701" --count 100 --source video.mp4

Controls: Q = quit early
"""

import os
import sys
import cv2
import argparse
import time
import numpy as np

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.config import DATA_DIR, INSIGHTFACE_MODEL, DET_SIZE, MIN_FACE_SIZE, BLUR_THRESHOLD

parser = argparse.ArgumentParser()
parser.add_argument("--name",   required=True,        help="Person name, e.g. 'ch 701'")
parser.add_argument("--count",  type=int, default=100, help="Target image count")
parser.add_argument("--cam",    type=int, default=0,   help="Camera index (default 0)")
parser.add_argument("--source", type=str, default=None, help="RTSP URL or video file path (overrides --cam)")
parser.add_argument("--interval", type=float, default=0.5, help="Min seconds between saves (default 0.5)")
args = parser.parse_args()

save_dir = os.path.join(DATA_DIR, args.name)
os.makedirs(save_dir, exist_ok=True)

# Count already existing images
existing = len([f for f in os.listdir(save_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
print(f"\n[INFO] Person: '{args.name}'")
print(f"[INFO] Save dir: {save_dir}")
print(f"[INFO] Already saved: {existing} images")
print(f"[INFO] Target: {args.count} more images\n")

from insightface.app import FaceAnalysis
detector = FaceAnalysis(name=INSIGHTFACE_MODEL, providers=["CPUExecutionProvider"])
detector.prepare(ctx_id=0, det_size=DET_SIZE)

source = args.source if args.source else args.cam
cap = cv2.VideoCapture(source)
if not cap.isOpened():
    print(f"[ERROR] Cannot open source: {source}")
    sys.exit(1)

# Flush initial black frames
for _ in range(5):
    cap.read()

captured   = 0
last_saved = 0.0

print(f"[RUNNING] Auto-capturing... Press Q to quit early\n")

while captured < args.count:
    ret, frame = cap.read()
    if not ret:
        print("[INFO] Stream ended.")
        break

    now = time.time()
    if now - last_saved < args.interval:
        # Still show preview even if not saving
        display = frame.copy()
        cv2.putText(display, f"'{args.name}'  {captured}/{args.count}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.imshow("Dataset Collection", display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
        continue

    faces = detector.get(frame)
    display = frame.copy()

    best_face = None
    best_area = 0

    for face in faces:
        x1, y1, x2, y2 = map(int, face.bbox)
        w, h = x2 - x1, y2 - y1

        # Size filter
        if w < MIN_FACE_SIZE or h < MIN_FACE_SIZE:
            continue

        # Blur filter
        face_crop = frame[max(0,y1):y2, max(0,x1):x2]
        if face_crop.size == 0:
            continue
        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        blur = cv2.Laplacian(gray, cv2.CV_64F).var()
        if blur < BLUR_THRESHOLD:
            continue

        area = w * h
        if area > best_area:
            best_area = area
            best_face = face

        cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(display, f"blur:{blur:.1f}", (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

    if best_face is not None:
        ts = int(time.time() * 1000)
        path = os.path.join(save_dir, f"{ts}.jpg")
        cv2.imwrite(path, frame)
        captured += 1
        last_saved = now
        print(f"  [{captured:03d}/{args.count}] Saved: {os.path.basename(path)}")

    status = f"'{args.name}'  {captured}/{args.count}  |  Q=quit"
    cv2.putText(display, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    if not faces:
        cv2.putText(display, "No face", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    cv2.imshow("Dataset Collection", display)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        print("\n[INFO] Quit by user.")
        break

cap.release()
cv2.destroyAllWindows()

total = existing + captured
print(f"\n✅ Done — {captured} new images saved (total: {total})")
print(f"   Folder: {save_dir}")
if captured > 0:
    print(f"\nNext step: python enroll.py")
