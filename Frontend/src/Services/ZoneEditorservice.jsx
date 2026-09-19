import axiosInstance from './axios';

export const fetchCameraZones = (cameraId) =>
  axiosInstance.get('/zones', { params: { cameraId } }).then(r => r.data.data || []);

export const fetchStoreZones = (storeId) =>
  axiosInstance.get('/zones', { params: { storeId } }).then(r => r.data.data || []);

export const createZone = (payload) =>
  axiosInstance.post('/zones', payload).then(r => r.data.data);

export const updateZone = (id, payload) =>
  axiosInstance.patch(`/zones/${id}`, payload).then(r => r.data.data);

export const updateZonePolygon = (id, polygon) =>
  axiosInstance.patch(`/zones/${id}/polygon`, { polygon }).then(r => r.data.data);

export const deleteZone = (id) =>
  axiosInstance.delete(`/zones/${id}`);

export const saveDwellRecord = (payload) =>
  axiosInstance.post('/zones/dwell', payload).then(r => r.data.data);

export const fetchDwellRecords = (zoneId, limit = 50) =>
  axiosInstance.get(`/zones/${zoneId}/dwell`, { params: { limit } }).then(r => r.data.data || []);
