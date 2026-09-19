"""
Creates dummy test screenshots for stock report PDF testing.
Run: python scripts/create_test_screenshot.py
"""
import cv2
import numpy as np
import os

output_dir = os.path.join(os.path.dirname(__file__), "..", "outputs", "stock_reports")
os.makedirs(output_dir, exist_ok=True)

def make_screenshot(filename, status="EMPTY", occupancy=12):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = (30, 30, 30)

    # Shelf lines
    for y in [120, 240, 360]:
        cv2.line(frame, (0, y), (640, y), (80, 80, 80), 2)

    # Empty boxes (red)
    for (x1, y1, x2, y2) in [(50,130,180,230),(200,130,330,230),(480,250,610,350)]:
        cv2.rectangle(frame, (x1,y1), (x2,y2), (30,30,220), 2)
        cv2.rectangle(frame, (x1,y1-18), (x1+60,y1), (30,30,220), -1)
        cv2.putText(frame, "empty", (x1+3,y1-4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255,255,255), 1)

    # Stocked boxes (green)
    for (x1, y1, x2, y2) in [(350,130,470,230),(50,250,180,350),(200,250,330,350)]:
        cv2.rectangle(frame, (x1,y1), (x2,y2), (34,197,94), 2)
        cv2.rectangle(frame, (x1,y1-18), (x1+80,y1), (34,197,94), -1)
        cv2.putText(frame, "non-empty", (x1+3,y1-4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255,255,255), 1)

    # Status banner
    cv2.rectangle(frame, (0,408), (640,480), (10,10,10), -1)
    icon = "[XX]" if status == "EMPTY" else "[!!]"
    color = (30,30,200) if status == "EMPTY" else (30,140,255)
    cv2.putText(frame, f"{icon} SHELF: {status}", (12,435), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)
    cv2.putText(frame, f"Occupancy: {occupancy}%", (330,435), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200,200,200), 1)
    cv2.putText(frame, "OOS: 3   Empty: 3   Reduced: 1", (12,468), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (200,200,200), 1)
    cv2.putText(frame, "CAM-3 | Shelf Monitor", (10,25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)

    path = os.path.join(output_dir, filename)
    cv2.imwrite(path, frame)
    print(f"Saved: {path}")
    return path

make_screenshot("cam3_20250719_143210.jpg", "EMPTY",     12)
make_screenshot("cam3_20250719_150530.jpg", "LOW STOCK", 38)
make_screenshot("cam3_20250719_162045.jpg", "EMPTY",     8)

print("Done! 3 test screenshots created.")
