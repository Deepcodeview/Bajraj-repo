"""
api/server.py — FastAPI server for Face Recognition
Endpoints:
  POST /recognize        — image upload → recognition result
  POST /enroll           — add new person images + re-enroll
  GET  /persons          — list enrolled persons
  GET  /events           — attendance log
  POST /session/reset    — reset session state
  GET  /health           — health check
"""

import os
import cv2
import numpy as np
import shutil
from datetime import datetime
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from core.recognizer import FaceRecognizer
from core.config import DATA_DIR, STATIC_DIR

app = FastAPI(title="Face Recognition API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single global recognizer instance
recognizer = FaceRecognizer()


@app.get("/health")
def health():
    return {
        "status":   "ok",
        "persons":  len(recognizer.db_names),
        "enrolled": recognizer.db_names,
    }


@app.post("/recognize")
async def recognize(file: UploadFile = File(...)):
    """Upload a frame/image → get face recognition results."""
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")

    nparr = np.frombuffer(raw, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(400, "Invalid image")

    annotated, results = recognizer.process_frame(frame)

    # Save annotated frame to static
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:20]
    out_path = os.path.join(STATIC_DIR, f"result_{ts}.jpg")
    cv2.imwrite(out_path, annotated)

    return {
        "faces":      results,
        "face_count": len(results),
        "timestamp":  datetime.now().isoformat(),
        "result_img": f"/static/result_{ts}.jpg",
    }


@app.post("/enroll")
async def enroll(
    name:  str = Form(...),
    files: list[UploadFile] = File(...),
):
    """Upload images for a new person and re-build embeddings."""
    person_dir = os.path.join(DATA_DIR, name)
    os.makedirs(person_dir, exist_ok=True)

    saved = 0
    for f in files:
        raw = await f.read()
        if not raw:
            continue
        ext = os.path.splitext(f.filename)[1] or ".jpg"
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:20]
        path = os.path.join(person_dir, f"{ts}{ext}")
        with open(path, "wb") as fp:
            fp.write(raw)
        saved += 1

    if saved == 0:
        raise HTTPException(400, "No valid images uploaded")

    # Re-run enrollment
    _run_enroll()
    recognizer.reload()

    return {"ok": True, "name": name, "images_saved": saved, "enrolled": recognizer.db_names}


@app.delete("/persons/{name}")
def delete_person(name: str):
    """Remove a person from enrollment."""
    person_dir = os.path.join(DATA_DIR, name)
    if not os.path.exists(person_dir):
        raise HTTPException(404, f"{name} not found")
    shutil.rmtree(person_dir)
    _run_enroll()
    recognizer.reload()
    return {"ok": True, "deleted": name, "enrolled": recognizer.db_names}


@app.get("/persons")
def list_persons():
    persons = []
    for p in sorted(os.listdir(DATA_DIR)):
        d = os.path.join(DATA_DIR, p)
        if os.path.isdir(d):
            count = len([f for f in os.listdir(d) if f.lower().endswith(('.jpg','.jpeg','.png'))])
            persons.append({"name": p, "images": count})
    return {"persons": persons, "total": len(persons)}


@app.get("/events")
def get_events():
    return {"events": recognizer.get_events(), "total": len(recognizer.events)}


@app.get("/analytics")
def get_analytics():
    return recognizer.get_analytics()


@app.post("/session/reset")
def reset_session():
    recognizer.reset_session()
    return {"ok": True, "message": "Session reset"}


# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _run_enroll():
    """Run enrollment programmatically."""
    import subprocess, sys
    subprocess.run([sys.executable, "enroll.py"], cwd=os.path.dirname(os.path.dirname(__file__)))
