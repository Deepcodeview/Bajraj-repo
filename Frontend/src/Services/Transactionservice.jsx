import axiosInstance from './axios';

export const getTransactions = (params) =>
  axiosInstance.get('/transactions', { params }).then(r => r.data).catch(() => ({ data: [] }));

export const getTransactionById = (id) =>
  axiosInstance.get(`/transactions/${id}`).then(r => r.data);

export const getTransactionSummary = (params) =>
  axiosInstance.get('/transactions/summary', { params }).then(r => r.data).catch(() => ({ data: null }));

export const getTransactionTrend = (params) =>
  axiosInstance.get('/transactions/trend', { params }).then(r => r.data).catch(() => ({ data: { trend: [] } }));

export const getPaymentMethodSplit = (params) =>
  axiosInstance.get('/transactions/payment-split', { params }).then(r => r.data).catch(() => ({ data: [] }));

export const exportTransactions = (params) =>
  axiosInstance.get('/transactions/export', { params, responseType: 'blob' }).then(r => r.data);
