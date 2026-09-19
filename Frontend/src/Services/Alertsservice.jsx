import axiosInstance from './axios';

export const getAlerts = (params) =>
  axiosInstance.get('/alerts', { params }).then(r => r.data);

export const getAlertById = (id) =>
  axiosInstance.get(`/alerts/${id}`).then(r => r.data);

export const acknowledgeAlert = (id) =>
  axiosInstance.patch(`/alerts/${id}/acknowledge`).then(r => r.data);

export const resolveAlert = (id, resolutionNotes) =>
  axiosInstance.patch(`/alerts/${id}/resolve`, { resolutionNotes }).then(r => r.data);

export const evaluateUnattendedCustomer = (sessionId) =>
  axiosInstance.post(`/alerts/evaluate/unattended/${sessionId}`).then(r => r.data);

export const getAlertReport = (params) =>
  axiosInstance.get('/alerts/report', { params }).then(r => r.data);

export const exportAlertReportPdf = (params) =>
  axiosInstance.get('/alerts/report/export/pdf', { params, responseType: 'blob' }).then(r => r.data);
