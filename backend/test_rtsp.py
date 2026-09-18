import cv2, os, time

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|buffer_size;4000000|stimeout;15000000|loglevel;quiet"

url = "rtsp://frameai:qweRty99@45.121.29.181:30100/Streaming/channels/102"
print(f"Connecting to: {url}")

cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
print(f"Opened: {cap.isOpened()}")

if cap.isOpened():
    print(f"Resolution: {int(cap.get(3))}x{int(cap.get(4))}")
    print(f"FPS: {cap.get(5)}")
    
    for i in range(5):
        ret, frame = cap.read()
        print(f"Frame {i+1}: ret={ret}, shape={frame.shape if ret and frame is not None else 'None'}")
        if ret and frame is not None:
            cv2.imwrite(f"test_frame_{i}.jpg", frame)
            print(f"  Saved test_frame_{i}.jpg")
            break
        time.sleep(1)
    cap.release()
else:
    print("FAILED to open stream")
