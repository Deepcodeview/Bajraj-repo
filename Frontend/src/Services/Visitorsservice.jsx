import axiosInstance from './axios';

// ── Visitors (Customer Sessions) ──────────────────────────────────
export const fetchCustomerSessions = async (params = {}) => {
  const res = await axiosInstance.get('/customer-sessions', { params });
  return res.data;
};

export const fetchCustomerReport = async (params = {}) => {
  const res = await axiosInstance.get('/customer-sessions/report', { params });
  return res.data.data;
};

export const fetchCustomerSummary = async (params = {}) => {
  const res = await axiosInstance.get('/customer-sessions/report/summary', { params });
  return res.data.data;
};
