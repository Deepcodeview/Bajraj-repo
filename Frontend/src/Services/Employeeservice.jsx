import axiosInstance from './axios';

export const getEmployees = (storeId) =>
  axiosInstance.get('/employees', { params: storeId ? { storeId } : {} }).then(r => r.data);

export const getEmployeeById = (id) =>
  axiosInstance.get(`/employees/${id}`).then(r => r.data);

export const createEmployee = (data) =>
  axiosInstance.post('/employees', data).then(r => r.data);

export const updateEmployee = (id, data) =>
  axiosInstance.patch(`/employees/${id}`, data).then(r => r.data);

export const deleteEmployee = (id) =>
  axiosInstance.delete(`/employees/${id}`).then(r => r.data);

export const getEmployeeReport = (params) =>
  axiosInstance.get('/employees/report', { params }).then(r => r.data);

export const exportEmployeeReportPdf = (params) =>
  axiosInstance.get('/employees/report/export/pdf', { params, responseType: 'blob' }).then(r => r.data);
