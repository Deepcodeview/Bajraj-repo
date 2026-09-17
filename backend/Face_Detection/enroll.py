"""
enroll.py — Enrollment script for smartstore Face Detection
Run from: /Users/shubhamchaudhari/project_vault/Deepak/smartstore/backend/Face_Detection/
Command: python enroll.py
Output: models/embeddings.npz
"""
import os
import sys
import numpy as np
import cv2

# Add backend to path so app.face.config works
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA_DIR        = os.path.join(os.path.dirname(__file__), "data_enhanced")
EMBEDDINGS_FILE = os.path.join(os.path.dirname(__file__), "models", "embeddings.npz")
os.makedirs(os.path.join(os.path.dirname(__file__), "models"), exist_ok=True)

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from insightface.app import FaceAnalysis
import onnxruntime as ort

# InsightFace for aligned face detection
fa = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
fa.prepare(ctx_id=0, det_size=(640, 640))

# Direct ONNX for crops where detection fails
REC_MODEL = os.path.expanduser('~/.insightface/models/buffalo_l/w600k_r50.onnx')
_sess = ort.InferenceSession(REC_MODEL, providers=['CPUExecutionProvider'])
_inp  = _sess.get_inputs()[0].name

def get_embedding(img):
    """Try InsightFace aligned detection first, fallback to direct ONNX."""
    # Try detection (works if face is detectable)
    faces = fa.get(img)
    if faces:
        face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
        return face.normed_embedding
    # Fallback: direct ONNX on full crop (already a face crop)
    resized = cv2.resize(img, (112, 112))
    blob = resized[:, :, ::-1].astype('float32')  # BGR→RGB
    blob = (blob - 127.5) / 127.5
    blob = blob.transpose(2, 0, 1)[None]
    emb  = _sess.run(None, {_inp: blob})[0][0]
    return emb / np.linalg.norm(emb)


names, embeddings = [], []

for person in sorted(os.listdir(DATA_DIR)):
    person_dir = os.path.join(DATA_DIR, person)
    if not os.path.isdir(person_dir):
        continue

    img_files = [f for f in sorted(os.listdir(person_dir))
                 if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    print(f"\n[{person}] {len(img_files)} images...")

    person_embeddings = []
    for img_file in img_files:
        img = cv2.imread(os.path.join(person_dir, img_file))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if cv2.Laplacian(gray, cv2.CV_64F).var() < 2.0:
            continue
        try:
            person_embeddings.append(get_embedding(img))
        except Exception:
            pass

    if not person_embeddings:
        print(f"  [SKIP] No faces detected for {person}")
        continue

    # K-means clustering — frontal aur side-angle alag embeddings
    emb_arr = np.array(person_embeddings)
    from sklearn.cluster import KMeans
    n_clusters = min(5, len(emb_arr))
    if n_clusters > 1:
        km = KMeans(n_clusters=n_clusters, random_state=0, n_init=10).fit(emb_arr)
        cluster_embs = []
        for c in range(n_clusters):
            cluster = emb_arr[km.labels_ == c]
            avg = np.mean(cluster, axis=0)
            avg /= np.linalg.norm(avg)
            cluster_embs.append(avg)
        for i, emb in enumerate(cluster_embs):
            names.append(person)
            embeddings.append(emb)
        print(f"  [OK] {person} — {len(person_embeddings)}/{len(img_files)} used, {n_clusters} clusters")
    else:
        avg = emb_arr[0] / np.linalg.norm(emb_arr[0])
        names.append(person)
        embeddings.append(avg)
        print(f"  [OK] {person} — 1 embedding")

if names:
    np.savez(EMBEDDINGS_FILE, names=np.array(names), embeddings=np.array(embeddings))
    print(f"\n✅ Saved {len(names)} person(s): {', '.join(names)}")
    print(f"   File: {EMBEDDINGS_FILE}")
else:
    print("\nNo persons enrolled.")
