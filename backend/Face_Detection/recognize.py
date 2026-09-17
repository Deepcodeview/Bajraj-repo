"""
recognize.py — Live face recognition from webcam
Run: python recognize.py
Press Q to quit.
"""

import cv2
from core.recognizer import FaceRecognizer

recognizer = FaceRecognizer()

cap = cv2.VideoCapture(0)
assert cap.isOpened(), "Cannot open camera"

cv2.namedWindow("Face Recognition", cv2.WINDOW_NORMAL)
print("Running — press Q to quit\n")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    annotated, results = recognizer.process_frame(frame)

    # Stats overlay
    cv2.putText(annotated, f"Faces: {len(results)}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    cv2.imshow("Face Recognition", annotated)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()

# Print session summary
events = recognizer.get_events()
print(f"\n=== Session Summary ===")
print(f"Total events: {len(events)}")
for e in events:
    print(f"  [{e['timestamp'][11:19]}] {e['type'].upper():8} {e['name']}  sim={e['sim']}")
