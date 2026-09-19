import axiosInstance from './axios';

export const AI_BASE = import.meta.env.VITE_AI_BASE || 'https://demo.cvframeiq.com/ai';

// ch1 = x01 (High Quality), ch2 = x02 (Low Quality/Substream)
const RTSP_BASE = 'rtsp://frameai:qweRty99@45.121.29.181:30100/Streaming/channels';

export const CAMERAS = [
  { id: 'cam1', name: 'CAM-01', label: 'Entrance',   ch1: `${RTSP_BASE}/101`, ch2: `${RTSP_BASE}/102` },
  { id: 'cam2', name: 'CAM-02', label: 'Main Floor', ch1: `${RTSP_BASE}/201`, ch2: `${RTSP_BASE}/202` },
  { id: 'cam3', name: 'CAM-03', label: 'Aisle A',    ch1: `${RTSP_BASE}/301`, ch2: `${RTSP_BASE}/302` },
  { id: 'cam4', name: 'CAM-04', label: 'Aisle B',    ch1: `${RTSP_BASE}/401`, ch2: `${RTSP_BASE}/402` },
  { id: 'cam5', name: 'CAM-05', label: 'Billing',    ch1: `${RTSP_BASE}/501`, ch2: `${RTSP_BASE}/502` },
  { id: 'cam6', name: 'CAM-06', label: 'Exit',       ch1: `${RTSP_BASE}/601`, ch2: `${RTSP_BASE}/602` },
  { id: 'cam7', name: 'CAM-07', label: 'Storage',    ch1: `${RTSP_BASE}/701`, ch2: `${RTSP_BASE}/702` },
  { id: 'cam8', name: 'CAM-08', label: 'Parking',    ch1: `${RTSP_BASE}/801`, ch2: `${RTSP_BASE}/802` },
];

export const getRtspUrl = (cam, quality) => quality === 'low' ? cam.ch2 : cam.ch1;

// Force substream (ch2/SD) for all jobs — ch1 HD causes H.265 decode failures
const _getJobRtsp = (cam) => cam.ch2;

// Start RTSP job → returns job_id
export const startCameraJob = async (cam, quality = 'high') => {
  const rtsp_url = cam.ch2; // Always use SD substream (H.264) — ch1 HD is H.265 which OpenCV fails to decode
  try {
    const res = await fetch(`${AI_BASE}/camera/rtsp/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rtsp_url,
        camera_id: cam.id,
        camera_name: cam.name,
        dataset_rtsp_url: cam.ch1,
        zones: '[]',
        entry_zone: '[]',
        exit_zone: '[]',
        conf: 0.35,
        mode: 'indoor',
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${res.status}`);
    }
    return res.json();
  } catch (e) {
    if (e.message && !e.message.includes('fetch')) throw e;
    throw new Error('AI server unreachable. Make sure Python backend is running on port 8001.');
  }
};

export const stopCameraJob = async (jobId) => {
  try { await fetch(`${AI_BASE}/camera/rtsp/stop/${jobId}`, { method: 'POST' }); } catch {}
};

export const stopAllJobs = async () => {
  try { await fetch(`${AI_BASE}/camera/rtsp/stop-all`, { method: 'POST' }); } catch {}
};

export const getJobStreamUrl = (jobId) => `${AI_BASE}/jobs/${jobId}/stream`;
export const getJobWsUrl = (jobId) => `${AI_BASE.replace('http', 'ws')}/ws/stream/${jobId}`;

export const fetchJobResult = async (jobId) => {
  try {
    const res = await fetch(`${AI_BASE}/result/${jobId}`);
    if (res.status === 404) return { stale: true };
    if (!res.ok) return null;
    const data = await res.json();
    if (data.status === 'FAILED' || data.status === 'COMPLETED') return { stale: true };
    return data;
  } catch { return null; }
};

// ── Node Backend ──────────────────────────────────────────────────
export const fetchStores = async () => {
  const res = await axiosInstance.get('/stores');
  return res.data.data || [];
};

export const fetchZones = async (storeId) => {
  const res = await axiosInstance.get('/zones', { params: storeId ? { storeId } : {} });
  return res.data.data || [];
};

export const fetchAlerts = async (storeId) => {
  const res = await axiosInstance.get('/alerts', { params: { limit: 10, status: 'OPEN', ...(storeId && { storeId }) } });
  return res.data.data || [];
};

export const acknowledgeAlert = async (alertId) => {
  const res = await axiosInstance.patch(`/alerts/${alertId}/acknowledge`);
  return res.data;
};

// Footfall from Node backend
export const fetchFootfallToday = async () => {
  try {
    const res = await axiosInstance.get('/footfall/today');
    return res.data.data || null;
  } catch { return null; }
};

export const fetchFootfallCurrent = async () => {
  try {
    const res = await axiosInstance.get('/footfall/current');
    return res.data.data || null;
  } catch { return null; }
};

// ── Python AI Server ──────────────────────────────────────────────
export const fetchAIHealth = async () => {
  try {
    const res = await fetch(`${AI_BASE}/health`);
    if (!res.ok) return { status: 'offline' };
    const data = await res.json();
    return { status: data.status === 'ok' ? 'ok' : 'offline' };
  } catch { return { status: 'offline' }; }
};

export const fetchAIEvents = async () => {
  try {
    const res = await fetch(`${AI_BASE}/camera/session/events`);
    if (!res.ok) return { events: [] };
    return res.json();
  } catch { return { events: [] }; }
};

export const fetchAIAnalytics = async () => {
  try {
    const res = await fetch(`${AI_BASE}/camera/retail/dashboard`);
    if (!res.ok) return null;
    return res.json();
  } catch { return null; }
};

export const fetchPersons = async () => {
  try {
    const res = await fetch(`${AI_BASE}/camera/tracking/active`);
    if (!res.ok) return { persons: [] };
    const data = await res.json();
    const persons = Object.values(data.cameras || {}).flatMap(c => c.persons || []);
    return { persons };
  } catch { return { persons: [] }; }
};
