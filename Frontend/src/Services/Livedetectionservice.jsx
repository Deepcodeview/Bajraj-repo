import axiosInstance from './axios';

export const AI_BASE = import.meta.env.VITE_AI_BASE || 'http://localhost:8001';

// ── 6 Real IP Cameras (Hikvision RTSP) ───────────────────────────
const RTSP_BASE = 'rtsp://frameai:qweRty99@45.121.29.181:30100/Streaming/channels';

export const CAMERAS = [
  { id: 'cam1', name: 'CAM-01', label: 'Entrance / Main Gate',  channel: 101, rtsp: `${RTSP_BASE}/101` },
  { id: 'cam2', name: 'CAM-02', label: 'Section A / Aisle',     channel: 201, rtsp: `${RTSP_BASE}/201` },
  { id: 'cam3', name: 'CAM-03', label: 'Section B / Shelves',   channel: 301, rtsp: `${RTSP_BASE}/301` },
  { id: 'cam4', name: 'CAM-04', label: 'Checkout / Exit',       channel: 401, rtsp: `${RTSP_BASE}/401` },
  { id: 'cam5', name: 'CAM-05', label: 'Storage / Back Area',   channel: 501, rtsp: `${RTSP_BASE}/501` },
  { id: 'cam6', name: 'CAM-06', label: 'Cash Counter',          channel: 601, rtsp: `${RTSP_BASE}/601` },
  { id: 'cam7', name: 'CAM-07', label: 'Parking / Exterior',    channel: 701, rtsp: `${RTSP_BASE}/701` },
  { id: 'cam8', name: 'CAM-08', label: 'Loading Dock',          channel: 801, rtsp: `${RTSP_BASE}/801` },
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
  try {
    const res = await fetch(`${AI_BASE}/health`);
    return res.ok ? res.json() : { status: 'error' };
  } catch { return { status: 'error' }; }
};

export const fetchAIEvents = async () => {
  try {
    const res = await fetch(`${AI_BASE}/camera/session/events`);
    return res.ok ? res.json() : { events: [] };
  } catch { return { events: [] }; }
};

export const fetchAIAnalytics = async () => {
  try {
    const res = await fetch(`${AI_BASE}/analytics`);
    return res.ok ? res.json() : null;
  } catch { return null; }
};

export const fetchPersons = async () => {
  try {
    const res = await fetch(`${AI_BASE}/persons`);
    return res.ok ? res.json() : { cameras: {} };
  } catch { return { cameras: {} }; }
};
