"""
add_employee.py — Naya employee enroll karo
Usage: python add_employee.py --name "Rahul" --cam cam6
       python add_employee.py --name "Rahul" --images /path/to/photos/

Steps:
1. CCTV dataset se crops nikalta hai (agar --cam diya)
2. Blur filter + CLAHE enhancement
3. Embeddings extract karke models/embeddings.npz mein add karta hai
"""
import os, sys, cv2, argparse, shutil
import numpy as np

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

parser = argparse.ArgumentParser()
parser.add_argument("--name",   required=True,  help="Employee name")
parser.add_argument("--cam",    default="",     help="Camera ID to collect from e.g. cam6")
parser.add_argument("--images", default="",     help="Direct folder with photos")
parser.add_argument("--limit",  type=int, default=2500, help="Max images to use")
args = parser.parse_args()

BASE        = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE, "data", args.name)
ENHANCED    = os.path.join(BASE, "data_enhanced", args.name)
EMB_FILE    = os.path.join(BASE, "models", "embeddings.npz")
DATASET_DIR = os.path.join(BASE, "..", "dataset_collection")

import onnxruntime as ort
REC_MODEL = os.path.expanduser("~/.insightface/models/buffalo_l/w600k_r50.onnx")
sess = ort.InferenceSession(REC_MODEL, providers=["CPUExecutionProvider"])
inp  = sess.get_inputs()[0].name

def get_embedding(img):
    r = cv2.resize(img, (112, 112))
    b = r[:, :, ::-1].astype("float32")
    b = (b - 127.5) / 127.5
    b = b.transpose(2, 0, 1)[None]
    e = sess.run(None, {inp: b})[0][0]
    return e / np.linalg.norm(e)

def clahe_enhance(img):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    cl = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(l)
    return cv2.cvtColor(cv2.merge([cl, a, b]), cv2.COLOR_LAB2BGR)

def unsharp(img):
    blur = cv2.GaussianBlur(img, (0, 0), 2.0)
    return cv2.addWeighted(img, 1.6, blur, -0.6, 0)

# ── Step 1: Source images collect karo ───────────────────────────────────────
os.makedirs(DATA_DIR, exist_ok=True)

if args.images:
    # Direct folder se copy karo
    src_files = [f for f in os.listdir(args.images) if f.lower().endswith(('.jpg','.jpeg','.png'))]
    for f in src_files[:args.limit]:
        shutil.copy(os.path.join(args.images, f), os.path.join(DATA_DIR, f))
    print(f"[{args.name}] {len(src_files[:args.limit])} images copied from {args.images}")

elif args.cam:
    # CCTV dataset se collect karo
    cam_dir = os.path.join(DATASET_DIR, args.cam)
    if not os.path.exists(cam_dir):
        print(f"ERROR: {cam_dir} not found")
        sys.exit(1)
    all_imgs = []
    for day in sorted(os.listdir(cam_dir)):
        img_dir = os.path.join(cam_dir, day, "images")
        if os.path.exists(img_dir):
            all_imgs += [os.path.join(img_dir, f) for f in os.listdir(img_dir) if f.endswith('.jpg')]
    all_imgs = sorted(all_imgs)[:args.limit]
    for src in all_imgs:
        shutil.copy(src, os.path.join(DATA_DIR, os.path.basename(src)))
    print(f"[{args.name}] {len(all_imgs)} images collected from {args.cam}")

else:
    if not os.path.exists(DATA_DIR) or not os.listdir(DATA_DIR):
        print(f"ERROR: data/{args.name}/ empty. Use --cam or --images")
        sys.exit(1)
    print(f"[{args.name}] Using existing data/{args.name}/")

# ── Step 2: Enhance ───────────────────────────────────────────────────────────
os.makedirs(ENHANCED, exist_ok=True)
files = [f for f in os.listdir(DATA_DIR) if f.lower().endswith(('.jpg','.jpeg','.png'))]
kept = 0
for f in files:
    img = cv2.imread(os.path.join(DATA_DIR, f))
    if img is None: continue
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if cv2.Laplacian(gray, cv2.CV_64F).var() < 15: continue
    img = clahe_enhance(img)
    img = unsharp(img)
    cv2.imwrite(os.path.join(ENHANCED, f), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    kept += 1
print(f"[{args.name}] Enhanced: {kept}/{len(files)} images kept")

# ── Step 3: Embeddings extract ────────────────────────────────────────────────
efiles = [f for f in os.listdir(ENHANCED) if f.lower().endswith(('.jpg','.jpeg','.png'))]
emb_list = []
for f in efiles:
    img = cv2.imread(os.path.join(ENHANCED, f))
    if img is None: continue
    try:
        emb_list.append(get_embedding(img))
    except Exception:
        pass
print(f"[{args.name}] Embeddings: {len(emb_list)}/{len(efiles)}")

if not emb_list:
    print("ERROR: No embeddings extracted")
    sys.exit(1)

# ── Step 4: K-Means clustering ────────────────────────────────────────────────
from sklearn.cluster import KMeans
emb_arr   = np.array(emb_list)
n_clusters = min(5, len(emb_arr))
km = KMeans(n_clusters=n_clusters, random_state=0, n_init=10).fit(emb_arr)
new_names, new_embs = [], []
for c in range(n_clusters):
    cluster = emb_arr[km.labels_ == c]
    avg = np.mean(cluster, axis=0)
    avg /= np.linalg.norm(avg)
    new_names.append(args.name)
    new_embs.append(avg)
print(f"[{args.name}] {n_clusters} clusters created")

# ── Step 5: Existing embeddings mein add karo ─────────────────────────────────
os.makedirs(os.path.dirname(EMB_FILE), exist_ok=True)
if os.path.exists(EMB_FILE):
    db = np.load(EMB_FILE, allow_pickle=True)
    # Remove old entries for this person (re-enroll case)
    old_names = db["names"].tolist()
    old_embs  = db["embeddings"].tolist()
    filtered  = [(n, e) for n, e in zip(old_names, old_embs) if n != args.name]
    if filtered:
        keep_names, keep_embs = zip(*filtered)
        final_names = list(keep_names) + new_names
        final_embs  = list(keep_embs)  + new_embs
    else:
        final_names = new_names
        final_embs  = new_embs
else:
    final_names = new_names
    final_embs  = new_embs

np.savez(EMB_FILE, names=np.array(final_names), embeddings=np.array(final_embs))
unique = list(set(final_names))
print(f"\n✅ Done! Enrolled persons: {unique}")
print(f"   Total embeddings: {len(final_names)} ({len(unique)} persons × ~5 clusters)")
print(f"   File: {EMB_FILE}")
