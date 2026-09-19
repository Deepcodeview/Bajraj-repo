import axiosInstance from './axios';

export const fetchCameraZones = async (cameraId) => {
  const res = await axiosInstance.get('/zones', { params: { cameraId } });
  return res.data.data || [];
};

export const createZone = async (payload) => {
  const res = await axiosInstance.post('/zones', payload);
  return res.data.data;
};

export const updateZone = async (id, payload) => {
  const res = await axiosInstance.patch(`/zones/${id}`, payload);
  return res.data.data;
};

export const deleteZone = async (id) => {
  await axiosInstance.delete(`/zones/${id}`);
};

export const saveDwellRecord = async (payload) => {
  // payload: { zone_id, camera_id, person_id, dwell_seconds, entered_at, exited_at }
  const res = await axiosInstance.post('/zones/dwell', payload);
  return res.data.data;
};

export const fetchDwellRecords = async (zoneId, limit = 50) => {
  const res = await axiosInstance.get(`/zones/${zoneId}/dwell`, { params: { limit } });
  return res.data.data || [];
};
