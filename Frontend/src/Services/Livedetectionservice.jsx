import axiosInstance from './axios';

export const AI_BASE = import.meta.env.VITE_AI_BASE || 'http://localhost:8001';

// ── 6 Real IP Cameras (Hikvision RTSP) ───────────────────────────
const RTSP_BASE = 'rtsp://frameai:qweRty99@45.121.29.181:30100/Streaming/channels';

export const CAMERAS = [
  { id: 'cam1', name: 'CAM-01', label: 'Entrance',   channel: 102, rtsp: `${RTSP_BASE}/102` },
  { id: 'cam2', name: 'CAM-02', label: 'Main Floor', channel: 202, rtsp: `${RTSP_BASE}/202` },
  { id: 'cam3', name: 'CAM-03', label: 'Aisle A',    channel: 302, rtsp: `${RTSP_BASE}/302` },
  { id: 'cam4', name: 'CAM-04', label: 'Aisle B',    channel: 402, rtsp: `${RTSP_BASE}/402` },
  { id: 'cam5', name: 'CAM-05', label: 'Billing',    channel: 502, rtsp: `${RTSP_BASE}/502` },
  { id: 'cam6', name: 'CAM-06', label: 'Exit',       channel: 602, rtsp: `${RTSP_BASE}/602` },
  { id: 'cam7', name: 'CAM-07', label: 'Storage',    channel: 702, rtsp: `${RTSP_BASE}/702` },
  { id: 'cam8', name: 'CAM-08', label: 'Parking',    channel: 802, rtsp: `${RTSP_BASE}/802` },
];

// Start RTSP job → returns job_id
export const startCameraJob = async (cam) => {
  try {
    const res = await fetch(`${AI_BASE}/camera/rtsp/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rtsp_url: cam.rtsp, camera_id: cam.id, camera_name: cam.name }),
    });
    return res.json();
  } catch (e) { throw new Error('AI server unreachable. Check Nginx /ai/ proxy config.'); }
};

export const stopCameraJob = async (jobId) => {
  try { await fetch(`${AI_BASE}/camera/rtsp/stop/${jobId}`, { method: 'POST' }); } catch {}
};

export const stopAllJobs = async () => {
  try { await fetch(`${AI_BASE}/camera/rtsp/stop-all`, { method: 'POST' }); } catch {}
};

export const getJobStreamUrl = (jobId) => `${AI_BASE}/jobs/${jobId}/stream`;

export const fetchJobResult = async (jobId) => {
  try {
    const res = await fetch(`${AI_BASE}/result/${jobId}`);
    if (res.status === 404) return null;
    return res.ok ? res.json() : null;
  } catch { return null; }
};

// ── Node Backend ──────────────────────────────────────────────────
export const fetchStores = async () => {
  const res = await axiosInstance.get('/stores');
  return res.data.data;
};

export const fetchZones = async (storeId) => {
  const res = await axiosInstance.get('/zones', { params: storeId ? { storeId } : {} });
  return res.data.data;
};

export const fetchAlerts = async (storeId) => {
  const res = await axiosInstance.get('/alerts', { params: { limit: 10, status: 'OPEN', ...(storeId && { storeId }) } });
  return res.data.data;
};

export const acknowledgeAlert = async (alertId) => {
  const res = await axiosInstance.patch(`/alerts/${alertId}/acknowledge`);
  return res.data;
};

// ── Python AI Server ──────────────────────────────────────────────
export const fetchAIHealth = async () => {
  const res = await fetch(`${AI_BASE}/health`);
  return res.json();
};

export const fetchAIEvents = async () => {
  const res = await fetch(`${AI_BASE}/events`);
  return res.json();
};

export const fetchAIAnalytics = async () => {
  const res = await fetch(`${AI_BASE}/analytics`);
  return res.json();
};

export const fetchPersons = async () => {
  const res = await fetch(`${AI_BASE}/persons`);
  return res.json();
};
