import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import {Alert, Button, Center,Card, Container, Group, Stack, Switch, Text, Title} from '@mantine/core';
import { ArrowLeft } from 'lucide-react';
import VideoLikePoseCanvas2D from "@/components/VideoLikePoseCanvas2D";
import TrackSelector from "@/components/TrackSelector";
import SpeedChart from "@/components/SpeedChart";
import { useGlobalStore } from '@/store/global';
import type { VideoRecord } from '@/api/types';

interface DisplayIdInfo {
  id: string;
  displayValue: number;
  label: string;
  type: 'jersey' | 'track';
  confidence: number;
  fallbackTrackId: number;
}

export default function TaskDetail() {
  const navigate = useNavigate();
  const { taskId } = useParams<{ taskId: string }>();
  const location = useLocation();
  const record = location.state?.record as VideoRecord;

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const setAspectRatio = useGlobalStore(s => s.setAspectRatio);
  const setVideoDuration = useGlobalStore(s => s.setVideoDuration);

  const [wsConnection, setWsConnection] = useState<WebSocket | null>(null);
  const [frameData, setFrameData] = useState<any>(null);
  const [retryInfo, setRetryInfo] = useState({ attempts: 0, maxRetries: 5 });

  // Display ID 选择相关状态 - 全局共享状态
  const [selectedDisplayId, setSelectedDisplayId] = useState<string | null>(null);
  const [availableDisplayIds, setAvailableDisplayIds] = useState<DisplayIdInfo[]>([]);
  const [renderMode, setRenderMode] = useState<'all' | 'single'>('single');

  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const maxReconnectAttempts = 5;

  const connectWebSocket = useCallback((taskId: string) => {
    if (wsConnection) {
      wsConnection.close();
    }

    const API_BASE = import.meta.env.VITE_API_BASE || '';
    const wsUrl = `${API_BASE.replace(/^http/, 'ws')}/ws/pose/${taskId}`;

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setRetryInfo(prev => ({ ...prev, attempts: 0 }));
      setFrameData(null);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('Received data', data);
        setFrameData(data);
      } catch (error) {
        console.error('WebSocket message parse error:', error);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onclose = (event) => {
      setWsConnection(null);

      // 若不是正常关闭，且还没达到最大尝试次数
      if (event.code !== 1000 && retryInfo.attempts < maxReconnectAttempts) {
        setRetryInfo(prev => ({ ...prev, attempts: prev.attempts + 1 }));

        reconnectTimeoutRef.current = setTimeout(() => {
          connectWebSocket(taskId);
        }, Math.min(1000 * Math.pow(2, retryInfo.attempts), 10000));
      }
    };

    setWsConnection(ws);
  }, [wsConnection, retryInfo.attempts]);

  const handleManualReconnect = useCallback(() => {
    if (taskId) {
      setRetryInfo({ attempts: 0, maxRetries: maxReconnectAttempts });
      setFrameData(null);
      connectWebSocket(taskId);
    }
  }, [taskId, connectWebSocket]);

  const handleDisplayIdsUpdate = (displayIds: DisplayIdInfo[]) => {
    setAvailableDisplayIds(displayIds);

    // 如果当前选择的Display ID不在新列表中，重置选择
    if (selectedDisplayId !== null && !displayIds.some(d => d.id === selectedDisplayId)) {
      if (displayIds.length > 0) {
        setSelectedDisplayId(displayIds[0].id);
      } else {
        setSelectedDisplayId(null);
      }
    }
  };

  // 视频加载后设置宽高比
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !setAspectRatio || !setVideoDuration) return;

    const handleLoaded = () => {
      if (video.videoWidth && video.videoHeight) {
        const ratio = video.videoWidth / video.videoHeight;
        setAspectRatio(ratio);
      }

      if (!isNaN(video.duration)) {
        setVideoDuration(video.duration); // 设置视频总时长（单位：秒）
      }
    };

    video.addEventListener('loadedmetadata', handleLoaded);
    return () => {
      video.removeEventListener('loadedmetadata', handleLoaded);
    };
  }, [setAspectRatio, setVideoDuration]);

  // 当模式变化时自动选择合适的Display ID
  useEffect(() => {
    if (renderMode === 'single' && selectedDisplayId === null && availableDisplayIds.length > 0) {
      setSelectedDisplayId(availableDisplayIds[0].id); // 自动选择第一个
    } else if (renderMode === 'all') {
      setSelectedDisplayId(null);
    }
  }, [renderMode, availableDisplayIds, selectedDisplayId]);

  useEffect(() => {
    if (taskId) {
      connectWebSocket(taskId);
    }

    return () => {
      if (wsConnection) {
        wsConnection.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [taskId]);

  if (!record || !taskId) {
    return (
        <Container size="xl" px="md">
          <Center h={400}>
            <Stack align="center">
              <Text>Video record not found</Text>
              <Button onClick={() => navigate('/history')} leftSection={<ArrowLeft size={16} />}>
                Back to History
              </Button>
            </Stack>
          </Center>
        </Container>
    );
  }

  return (
      <Container size="xl" px="md">
        {/* 页面头部 */}
        <Group justify="space-between" align="center" mb="xl">
          <Button
              variant="outline"
              onClick={() => navigate('/history')}
              leftSection={<ArrowLeft size={16} />}
          >
            Back
          </Button>
          <Title order={2}>Video Analysis: {record.filename}</Title>
        </Group>

        {/* 主要内容区域 - 垂直堆叠布局 */}
        <Stack gap="xl">
          {/* 上面：处理后的视频 */}
          <Card withBorder p="lg">
            <Stack gap="md">
              <Text fw={600} size="lg">📹 Processed Video</Text>
              <video
                  ref={videoRef}
                  src={record.output_video_url}
                  controls
                  style={{
                    width: '100%',
                    height: 'auto',
                    borderRadius: '4px'
                  }}
              />
            </Stack>
          </Card>

          {/* 中间：Pose Canvas */}
          <Card withBorder p="lg">
            <Stack gap="md">
              <Group justify="space-between" align="center">
                {/* 性能提示 */}
                <Alert color="green" variant="light">
                  🚀 Single track mode enabled for better performance
                </Alert>
                <Switch
                    label="Single Track Mode"
                    checked={renderMode === 'single'}
                    onChange={(e) => setRenderMode(e.currentTarget.checked ? 'single' : 'all')}
                    color="green"
                    size="md"
                />
              </Group>

              {/* Track 选择器 - 只在单人模式显示 */}
              {renderMode === 'single' && (
                  <TrackSelector
                      availableDisplayIds={availableDisplayIds}
                      selectedDisplayId={selectedDisplayId}
                      onDisplayIdChange={setSelectedDisplayId}
                  />
              )}

              <Text fw={600} size="lg" mt='lg'>🎯 Pose Tracking</Text>

              <VideoLikePoseCanvas2D
                  frameData={frameData}
                  onManualReconnect={handleManualReconnect}
                  selectedDisplayId={selectedDisplayId}
                  onDisplayIdsUpdate={handleDisplayIdsUpdate}
                  targetFps={30}
                  bufferSize={60}
              />

              {/* 下面：速度图表 */}
              <Text fw={600} size="lg" mt="xl">📊 Speed Chart</Text>
              <SpeedChart
                  frameData={frameData}
                  selectedDisplayId={selectedDisplayId}
                  showAllTracks={renderMode === 'all'}
              />
            </Stack>
          </Card>
        </Stack>
      </Container>
  );
}
