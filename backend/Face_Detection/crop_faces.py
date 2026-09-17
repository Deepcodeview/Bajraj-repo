"""
crop_faces.py — Full frame images se face crops nikalo
Purani images replace ho jayengi face crops se
Run: python crop_faces.py --name Vishal
"""
import os, sys, cv2, argparse
import numpy as np

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

parser = argparse.ArgumentParser()
parser.add_argument("--name", required=True)
parser.add_argument("--padding", type=float, default=0.4, help="Face ke around padding, default 0.4")
args = parser.parse_args()

DATA_DIR   = os.path.join(os.path.dirname(__file__), "data", args.name)
CROP_DIR   = os.path.join(os.path.dirname(__file__), "data", args.name + "_crops")
os.makedirs(CROP_DIR, exist_ok=True)

from insightface.app import FaceAnalysis
app = FaceAnalysis(name="buffalo_s", providers=["CPUExecutionProvider"])
app.prepare(ctx_id=0, det_size=(1280, 1280))

imgs = [f for f in sorted(os.listdir(DATA_DIR)) if f.lower().endswith(('.jpg','.jpeg','.png'))]
print(f"\n[{args.name}] {len(imgs)} images processing...\n")

saved = 0
skipped = 0

for fname in imgs:
    img = cv2.imread(os.path.join(DATA_DIR, fname))
    if img is None:
        continue

    faces = app.get(img)
    if not faces:
        skipped += 1
        continue

    # Sabse bada face lo
    face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]))
    x1, y1, x2, y2 = map(int, face.bbox)
    w, h = x2 - x1, y2 - y1

    # Padding add karo
    pad_x = int(w * args.padding)
    pad_y = int(h * args.padding)
    H, W  = img.shape[:2]

    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(W, x2 + pad_x)
    y2 = min(H, y2 + pad_y)

    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        skipped += 1
        continue

    # 256x256 pe resize — enroll ke liye optimal
    crop = cv2.resize(crop, (256, 256))

    out_path = os.path.join(CROP_DIR, fname)
    cv2.imwrite(out_path, crop)
    saved += 1

    if saved % 50 == 0:
        print(f"  {saved}/{len(imgs)} done...")

print(f"\n✅ Crops saved: {saved}  |  Skipped: {skipped}")
print(f"   Folder: {CROP_DIR}")
print(f"\nAb purana folder replace karo:")
print(f"  mv {DATA_DIR} {DATA_DIR}_old")
print(f"  mv {CROP_DIR} {DATA_DIR}")
print(f"  python enroll.py")
