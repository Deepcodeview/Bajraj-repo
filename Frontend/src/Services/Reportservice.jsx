import axiosInstance from './axios';

export const getReportsSummary = () =>
  axiosInstance.get('/reports/summary').then(r => r.data);

export const getReportsHistory = (params) =>
  axiosInstance.get('/reports', { params }).then(r => r.data);

export const generateReport = (data) =>
  axiosInstance.post('/reports/generate', data).then(r => r.data);

export const downloadReport = (id) =>
  axiosInstance.get(`/reports/export/${id}`, { responseType: 'blob' }).then(r => r.data);

export const getScheduledReports = () =>
  axiosInstance.get('/reports/scheduled').then(r => r.data);

export const createScheduledReport = (data) =>
  axiosInstance.post('/reports/scheduled', data).then(r => r.data);

// Footfall reports (from footfall module)
export const getFootfallToday = () =>
  axiosInstance.get('/footfall/today').then(r => r.data);

export const getFootfallRange = (start_date, end_date) =>
  axiosInstance.get('/footfall/range', { params: { start_date, end_date } }).then(r => r.data);
