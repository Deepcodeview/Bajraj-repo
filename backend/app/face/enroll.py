"""
enroll.py — Enrollment script
Place images in: data/<person_name>/<any>.jpg
Run: python enroll.py
Output: models/embeddings.npz
"""

import os
import numpy as np
import cv2
from insightface.app import FaceAnalysis
from core.config import (
    DATA_DIR, EMBEDDINGS_FILE, INSIGHTFACE_MODEL, DET_SIZE,
    MIN_FACE_SIZE, BLUR_THRESHOLD,
)

app = FaceAnalysis(name=INSIGHTFACE_MODEL, providers=["CPUExecutionProvider"])
app.prepare(ctx_id=0, det_size=DET_SIZE)


def is_quality_ok(img, face):
    x1, y1, x2, y2 = map(int, face.bbox)
    w, h = x2 - x1, y2 - y1
    if w < MIN_FACE_SIZE or h < MIN_FACE_SIZE:
        return False, "too small"
    crop = img[max(0, y1):y2, max(0, x1):x2]
    if crop.size == 0:
        return False, "empty crop"
    blur = cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
    if blur < BLUR_THRESHOLD:
        return False, f"blurry ({blur:.1f})"
    return True, "ok"


names, embeddings = [], []

for person in sorted(os.listdir(DATA_DIR)):
    person_dir = os.path.join(DATA_DIR, person)
    if not os.path.isdir(person_dir):
        continue

    person_embeddings = []
    img_files = [f for f in sorted(os.listdir(person_dir))
                 if f.lower().endswith(('.jpg', '.jpeg', '.png'))]

    print(f"\n[{person}] Processing {len(img_files)} images...")

    for img_file in img_files:
        img_path = os.path.join(person_dir, img_file)
        img = cv2.imread(img_path)
        if img is None:
            continue

        faces = app.get(img)
        if not faces:
            print(f"  [WARN] No face: {img_file}")
            continue

        # Pick largest face
        face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]))

        ok, reason = is_quality_ok(img, face)
        if not ok:
            print(f"  [SKIP] {reason}: {img_file}")
            continue

        person_embeddings.append(face.normed_embedding)

    if not person_embeddings:
        print(f"  [SKIP] No valid faces for {person}")
        continue

    # Average embedding
    avg = np.mean(person_embeddings, axis=0)
    avg /= np.linalg.norm(avg)

    names.append(person)
    embeddings.append(avg)
    print(f"  [OK] Enrolled {person} — {len(person_embeddings)}/{len(img_files)} images used")

if not names:
    print("\nNo persons enrolled. Add images to data/<name>/ folders.")
else:
    np.savez(EMBEDDINGS_FILE, names=np.array(names), embeddings=np.array(embeddings))
    print(f"\n✅ Saved {len(names)} person(s) to {EMBEDDINGS_FILE}")
    print(f"   Enrolled: {', '.join(names)}")
