import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error?.response?.status;
    // An expired or invalid session must return the operator to sign-in rather
    // than leaving the workstation in a half-authenticated state.
    if (status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      if (!window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/signup')) {
        window.location.assign('/login');
      }
    }
    console.error('[API Error]', error?.response?.data || error.message);
    return Promise.reject(error?.response?.data || error);
  }
);

export default api;
