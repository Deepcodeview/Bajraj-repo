import axiosInstance from './axios';

export const getCameras = (params) =>
  axiosInstance.get('/cameras', { params }).then(r => r.data);

export const createCamera = (data) =>
  axiosInstance.post('/cameras', data).then(r => r.data);

export const updateCamera = (id, data) =>
  axiosInstance.patch(`/cameras/${id}`, data).then(r => r.data);

export const deleteCamera = (id) =>
  axiosInstance.delete(`/cameras/${id}`).then(r => r.data);
