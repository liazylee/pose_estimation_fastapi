import axios from 'axios';
import axiosRetry from 'axios-retry';
import { notifications } from '@mantine/notifications';
import { useUIStore } from '@/store/ui';

const API_BASE = import.meta.env.VITE_API_BASE || '';

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: false,
  timeout: 60_000,
});

axiosRetry(api, { retries: 2, retryDelay: axiosRetry.exponentialDelay });

api.interceptors.request.use((config) => {
  useUIStore.getState().increment();
  return config;
});

api.interceptors.response.use(
  (res) => { useUIStore.getState().decrement(); return res; },
  (error) => {
    useUIStore.getState().decrement();
    const message = error?.response?.data?.detail || error.message || '网络错误';
    notifications.show({ title: '请求失败', message, color: 'red' });
    return Promise.reject(error);
  }
);

export default api;


