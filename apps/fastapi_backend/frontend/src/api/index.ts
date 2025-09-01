import api from './client';
import type { HealthResponse, UploadResponse, TaskStatus, StreamsResponse, VideoRecordsResponse } from './types';

export const getHealth = () => api.get<HealthResponse>('/health').then(r => r.data);
export const getAIHealth = () => api.get('/api/ai/health').then(r => r.data);

export const upload = (file: File, onProgress?: (p: number) => void, controller?: AbortController) =>
  api.post<UploadResponse>('/upload', (() => {
    const form = new FormData();
    form.append('file', file);
    return form;
  })(), {
    signal: controller?.signal,
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (e.total) onProgress?.(Math.round((e.loaded / e.total) * 100));
    },
    timeout: 0,
  }).then(r => r.data);

export const getTaskStatus = (taskId: string) => api.get<TaskStatus>(`/status/${taskId}`).then(r => r.data);
export const getPipelineStatus = (taskId: string) => api.get(`/api/ai/pipeline/${taskId}/status`).then(r => r.data);
export const getResult = (taskId: string) => api.get(`/result/${taskId}`).then(r => r.data);

export const getStreams = () => api.get<StreamsResponse>('/streams').then(r => r.data);
export const stopStream = (taskId: string) => api.post(`/streams/${taskId}/stop`).then(r => r.data);
export const getStreamStatus = (taskId: string) => api.get(`/streams/${taskId}/status`).then(r => r.data);

export const getAnnotationRtsp = (taskId: string) => api.get(`/api/annotation/${taskId}/rtsp_url`).then(r => r.data);
export const getAnnotationVideos = (taskId: string) => api.get(`/api/annotation/${taskId}/videos`).then(r => r.data);
export const getAnnotationStatus = (taskId: string) => api.get(`/api/annotation/${taskId}/status`).then(r => r.data);

export const startPipeline = (taskId: string, config?: any) => api.post(`/api/ai/pipeline/start`, { task_id: taskId, config }).then(r => r.data);
export const stopPipeline = (taskId: string) => api.post(`/api/ai/pipeline/${taskId}/stop`).then(r => r.data);

export const getVideoRecords = (limit: number = 50, skip: number = 0) => 
  api.get<VideoRecordsResponse>(`/records?limit=${limit}&skip=${skip}`).then(r => r.data);


