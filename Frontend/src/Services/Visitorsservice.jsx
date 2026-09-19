import axiosInstance from './axios';

// Customer Sessions CRUD
export const fetchCustomerSessions = (params = {}) =>
  axiosInstance.get('/customer-sessions', { params }).then(r => r.data);

export const fetchCustomerSessionById = (id) =>
  axiosInstance.get(`/customer-sessions/${id}`).then(r => r.data);

export const createCustomerSession = (data) =>
  axiosInstance.post('/customer-sessions', data).then(r => r.data);

export const assignEmployeeToSession = (id, employeeId) =>
  axiosInstance.patch(`/customer-sessions/${id}/assign-employee`, { employeeId }).then(r => r.data);

export const updateSessionZone = (id, zoneId) =>
  axiosInstance.patch(`/customer-sessions/${id}/zone`, { zoneId }).then(r => r.data);

export const endCustomerSession = (id, status = 'COMPLETED') =>
  axiosInstance.patch(`/customer-sessions/${id}/end`, { status }).then(r => r.data);

// Customer Count (live)
export const getCustomerCount = (storeId) =>
  axiosInstance.get('/customer-sessions/count', { params: storeId ? { storeId } : {} }).then(r => r.data);

// Reports
export const fetchCustomerReport = (params = {}) =>
  axiosInstance.get('/customer-sessions/report', { params }).then(r => r.data);

export const fetchCustomerSummary = (params = {}) =>
  axiosInstance.get('/customer-sessions/report/summary', { params }).then(r => r.data);

export const exportCustomerReportPdf = (params = {}) =>
  axiosInstance.get('/customer-sessions/report/export/pdf', { params, responseType: 'blob' }).then(r => r.data);
