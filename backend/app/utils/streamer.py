import queue
import threading

class FrameStreamer:
    def __init__(self):
        self.queues = {}
        self._lock = threading.Lock()

    def register(self, job_id):
        q = queue.Queue(maxsize=3)
        with self._lock:
            if job_id not in self.queues:
                self.queues[job_id] = []
            self.queues[job_id].append(q)
        return q

    def unregister(self, job_id, q):
        with self._lock:
            if job_id in self.queues:
                if q in self.queues[job_id]:
                    self.queues[job_id].remove(q)
                if not self.queues[job_id]:
                    del self.queues[job_id]

    def put(self, job_id, jpeg_bytes):
        with self._lock:
            subscribers = list(self.queues.get(job_id, []))
        for q in subscribers:
            try:
                if q.full():
                    q.get_nowait()  # Drop oldest frame to maintain real-time
                q.put_nowait(jpeg_bytes)
            except Exception:
                pass

frame_streamer = FrameStreamer()
