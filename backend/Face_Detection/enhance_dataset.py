"""
enhance_dataset.py — Improve training data quality before enrollment
1. Remove blurry images (blur < BLUR_MIN)
2. CLAHE contrast enhancement
3. Sharpen with unsharp mask
Run: python enhance_dataset.py
"""
import os, cv2, shutil, numpy as np

DATA_DIR   = os.path.join(os.path.dirname(__file__), "data")
BLUR_MIN   = 15.0   # discard below this
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data_enhanced")

def clahe_enhance(img):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    cl = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(l)
    return cv2.cvtColor(cv2.merge([cl, a, b]), cv2.COLOR_LAB2BGR)

def unsharp_mask(img, strength=0.6):
    blur = cv2.GaussianBlur(img, (0, 0), 2.0)
    return cv2.addWeighted(img, 1 + strength, blur, -strength, 0)

def process_person(person_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    files = [f for f in os.listdir(person_dir) if f.lower().endswith(('.jpg','.jpeg','.png'))]
    kept = discarded = 0
    for f in files:
        img = cv2.imread(os.path.join(person_dir, f))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.Laplacian(gray, cv2.CV_64F).var()
        if blur < BLUR_MIN:
            discarded += 1
            continue
        img = clahe_enhance(img)
        img = unsharp_mask(img)
        cv2.imwrite(os.path.join(out_dir, f), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        kept += 1
    return kept, discarded

if __name__ == "__main__":
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)

    for person in sorted(os.listdir(DATA_DIR)):
        person_dir = os.path.join(DATA_DIR, person)
        if not os.path.isdir(person_dir):
            continue
        out_dir = os.path.join(OUTPUT_DIR, person)
        kept, discarded = process_person(person_dir, out_dir)
        print(f"[{person}] kept={kept}  discarded={discarded}  total={kept+discarded}")

    print(f"\n✅ Enhanced data saved to: {OUTPUT_DIR}")
    print("Now update enroll.py DATA_DIR to data_enhanced and run: python enroll.py")
