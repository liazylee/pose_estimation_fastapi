export type HealthResponse = {
  status: 'healthy' | 'degraded' | string;
  timestamp: string;
  services: Record<string, any>;
  ai_services_summary?: any;
};

export type AIPipelineHealth = any;

export type UploadResponse = {
  task_id: string;
  message: string;
  stream_url?: string;
};

export type TaskStatus = {
  task_id: string;
  status: string;
  progress?: string | number;
  created_at?: string;
  updated_at?: string | null;
  error?: string | null;
};

export type StreamInfo = {
  task_id?: string;
  active?: boolean;
  rtsp_url?: string | null;
  annotations_rtsp_url?: string | null;
  created_at?: string | null;
};

export type StreamsResponse = {
  active_streams: Array<Record<string, any>>;
  count: number;
};

export type VideoRecord = {
  _id: string;
  task_id: string;
  filename: string;
  file_size: number;
  created_at: string;
  status: string;
  output_video_path: string;
  stream_url: string;
  output_video_url: string;
  duration?: number;
  [key: string]: any;
};

export type VideoRecordsResponse = {
  records: VideoRecord[];
  count: number;
  limit: number;
  skip: number;
};


