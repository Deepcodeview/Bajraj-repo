import axiosInstance from './axios';

export const getMe = () =>
  axiosInstance.get('/auth/me').then(r => r.data);

export const createAdmin = (data) =>
  axiosInstance.post('/auth/admins', data).then(r => r.data);

export const getStores = () =>
  axiosInstance.get('/stores').then(r => r.data);

export const createStore = (data) =>
  axiosInstance.post('/stores', data).then(r => r.data);

export const getOrganizations = () =>
  axiosInstance.get('/organizations').then(r => r.data);

export const updateOrganization = (id, data) =>
  axiosInstance.patch(`/organizations/${id}`, data).then(r => r.data);
