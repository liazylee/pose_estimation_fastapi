import axios from 'axios';
import axiosRetry from 'axios-retry';
import {notifications} from '@mantine/notifications';
import { useGlobalStore } from '@/store/global';

const baseURL = import.meta.env.DEV ? '' : import.meta.env.VITE_API_BASE || '';

// 默认 API 实例（全局请求用）
export const api = axios.create({
    baseURL,
    timeout: 60000,
    withCredentials: false,
});

axiosRetry(api, {
    retries: 2,
    retryDelay: axiosRetry.exponentialDelay,
});

api.interceptors.response.use(
    (res) => res,
    (error) => {
        const message =
            error?.response?.data?.detail ||
            error?.response?.data?.message ||
            error.message ||
            'Internal Server Error';
        notifications.show({ title: 'Request Failed', message, color: 'red' });
        return Promise.reject(error);
    }
);

// 特殊的 stream 状态重试 API
export const streamApi = axios.create({
    baseURL: import.meta.env.DEV ? '/hls' : import.meta.env.VITE_API_HLS || '',
    timeout: 20000,  // 不宜过长，HLS 应该快速响应
    headers: {
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Expires': '0',
        'Accept': 'application/vnd.apple.mpegurl',
    },
});

axiosRetry(streamApi, {
    retries: 20,
    retryDelay: () => 1000, // 每次失败后等待 1 秒
    retryCondition: (error) => {
        const is404 = error.response?.status === 404;
        const url = error.config?.url ?? '';
        const isM3u8 = url.endsWith('.m3u8');
        return is404 && isM3u8;
    },
});

// 响应拦截器：只在请求 .m3u8 并非 404 时，设置 isM3u8Ready 为 true
streamApi.interceptors.response.use(
    (res) => {
        const url = res.config?.url ?? '';
        if (url.endsWith('.m3u8')) {
            const setM3u8Ready = useGlobalStore.getState().setM3u8Ready;
            setM3u8Ready(true); // 成功，说明 m3u8 就绪
        }
        return res;
    },
    (error) => {
        return Promise.reject(error);
    }
);
