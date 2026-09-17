"""
capture.py — Webcam enrollment image capture
Usage: python capture.py --name Shubham --count 20
SPACE = capture, Q = quit
"""

import cv2
import os
import argparse
from insightface.app import FaceAnalysis
from core.config import DATA_DIR, INSIGHTFACE_MODEL, DET_SIZE

parser = argparse.ArgumentParser()
parser.add_argument("--name",  required=True,        help="Person name")
parser.add_argument("--count", type=int, default=20, help="Number of images to capture")
parser.add_argument("--cam",   type=int, default=0,  help="Camera index")
args = parser.parse_args()

save_dir = os.path.join(DATA_DIR, args.name)
os.makedirs(save_dir, exist_ok=True)

# Load face detector for live preview
detector = FaceAnalysis(name=INSIGHTFACE_MODEL, providers=["CPUExecutionProvider"])
detector.prepare(ctx_id=0, det_size=DET_SIZE)

cap = cv2.VideoCapture(args.cam)
assert cap.isOpened(), f"Cannot open camera {args.cam}"
for _ in range(5): cap.read()  # flush black frames

captured = 0
print(f"Capturing {args.count} images for '{args.name}' — SPACE=capture, Q=quit")

while captured < args.count:
    ret, frame = cap.read()
    if not ret:
        break

    display = frame.copy()

    # Draw face boxes
    faces = detector.get(frame)
    for face in faces:
        x1, y1, x2, y2 = map(int, face.bbox)
        cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)

    status = f"'{args.name}'  {captured}/{args.count}  |  SPACE=capture  Q=quit"
    cv2.putText(display, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    if faces:
        cv2.putText(display, f"{len(faces)} face(s) detected", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    else:
        cv2.putText(display, "No face detected", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    cv2.imshow(f"Capture — {args.name}", display)

    key = cv2.waitKey(1) & 0xFF
    if key == ord(" "):
        if not faces:
            print("  [SKIP] No face detected — try again")
            continue
        path = os.path.join(save_dir, f"{captured+1:02d}.jpg")
        cv2.imwrite(path, frame)
        captured += 1
        print(f"  Saved {path}")
    elif key == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
print(f"\nDone — {captured} image(s) saved to '{save_dir}/'")
print("Now run: python enroll.py")
