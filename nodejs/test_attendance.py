import requests
import uuid
from datetime import datetime, timezone

BACKEND_URL = "http://localhost:8000/api/attendance/ai-event"
API_KEY = "smart-retail-ai-key-2025"

# ✅ Replace these with actual values from your DB
CAMERA_CODE = "CAM-001"      # cameras.camera_code (status must be ACTIVE)
EMPLOYEE_CODE = "EMP-001"    # employees.employee_code (status must be ACTIVE)


def send_attendance(camera_id: str, employee_id: str, confidence: float = 0.95):
    payload = {
        "eventId": str(uuid.uuid4()),
        "cameraId": camera_id,
        "employeeId": employee_id,
        "eventType": "FACE_RECOGNIZED",
        "confidence": confidence,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    response = requests.post(
        BACKEND_URL,
        json=payload,
        headers={"x-ai-service-key": API_KEY},
        timeout=10,
    )

    data = response.json()
    print(f"Status : {response.status_code}")
    print(f"Response: {data}")

    if data.get("processed"):
        action = data.get("attendanceAction")
        name = data.get("employee", {}).get("name")
        print(f"✅ {name} marked {action}")
    else:
        print(f"⚠️  Not processed — reason: {data.get('reason') or data.get('message')}")

    return data


if __name__ == "__main__":
    print("--- Sending attendance event (face detected) ---")
    send_attendance(CAMERA_CODE, EMPLOYEE_CODE)
