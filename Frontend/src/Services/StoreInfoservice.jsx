import axiosInstance from './axios';

// Organizations
export const getOrganizations = () =>
  axiosInstance.get('/organizations').then(r => r.data);

export const getOrganizationById = (id) =>
  axiosInstance.get(`/organizations/${id}`).then(r => r.data);

export const createOrganization = (data) =>
  axiosInstance.post('/organizations', data).then(r => r.data);

export const updateOrganization = (id, data) =>
  axiosInstance.patch(`/organizations/${id}`, data).then(r => r.data);

// Stores
export const getStores = () =>
  axiosInstance.get('/stores').then(r => r.data);

export const getStoreById = (id) =>
  axiosInstance.get(`/stores/${id}`).then(r => r.data);

export const createStore = (data) =>
  axiosInstance.post('/stores', data).then(r => r.data);
