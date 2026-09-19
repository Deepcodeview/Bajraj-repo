import axiosInstance from './axios';

export const getMe = () =>
  axiosInstance.get('/auth/me').then(r => r.data);

export const getStores = () =>
  axiosInstance.get('/stores').then(r => r.data);

export const getAlertCount = (storeId) =>
  axiosInstance.get('/alerts', {
    params: { status: 'OPEN', limit: 1, ...(storeId && { storeId }) }
  }).then(r => r.data.pagination?.total || 0);
