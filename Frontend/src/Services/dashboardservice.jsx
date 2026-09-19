import axiosInstance from './axios';

// Footfall
export const getFootfallToday = () =>
  axiosInstance.get('/footfall/today').then(r => r.data);

export const getFootfallCurrent = () =>
  axiosInstance.get('/footfall/current').then(r => r.data);

export const getFootfallRange = (start_date, end_date) =>
  axiosInstance.get('/footfall/range', { params: { start_date, end_date } }).then(r => r.data);

// Customer count (live visitors in store)
export const getCustomerCount = (storeId) =>
  axiosInstance.get('/customer-sessions/count', { params: storeId ? { storeId } : {} }).then(r => r.data);

// Stores
export const getStores = () =>
  axiosInstance.get('/stores').then(r => r.data);

// Alerts summary
export const getAlerts = (params) =>
  axiosInstance.get('/alerts', { params }).then(r => r.data);

// Attendance summary
export const getAttendanceSummary = (params) =>
  axiosInstance.get('/attendance/report/summary', { params }).then(r => r.data);
