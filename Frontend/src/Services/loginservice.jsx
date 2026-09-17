import axiosInstance from './axios';

export const loginAPI = async (email, password) => {
  try {
    const response = await axiosInstance.post('/auth/login', { email, password });
    return response.data;
  } catch (error) {
    console.error("Login API Error:", error);
    // Extract meaningful error message
    const errorMsg = error.response?.data?.message 
      || (typeof error.response?.data === 'string' ? error.response.data : null)
      || error.message 
      || 'Network error occurred';
      
    throw new Error(errorMsg);
  }
};
