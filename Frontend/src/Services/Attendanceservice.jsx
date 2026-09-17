import axiosInstance from './axios';

export const getAttendanceReport = (params) =>
  axiosInstance.get('/attendance/report', { params }).then(r => r.data);

export const getAttendanceSummary = (params) =>
  axiosInstance.get('/attendance/report/summary', { params }).then(r => r.data);

export const getAttendanceTrend = (params) =>
  axiosInstance.get('/attendance/report/trend', { params }).then(r => r.data);

export const getLiveLog = (params) =>
  axiosInstance.get('/attendance/report/live-log', { params }).then(r => r.data);

export const exportAttendancePdf = (params) =>
  axiosInstance.get('/attendance/report/export/pdf', { params, responseType: 'blob' }).then(r => r.data);
