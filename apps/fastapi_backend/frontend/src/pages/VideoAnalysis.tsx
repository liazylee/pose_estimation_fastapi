import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Stack,
  Button,
  Badge,
  Text,
  Group,
  Card,
  Loader,
  Center,
  Title,
  Container,
  SimpleGrid
} from '@mantine/core';
import { ArrowLeft } from 'lucide-react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import type { VideoRecord } from '../api/types';
import VideoLikePoseCanvas2D from '../components/VideoLikePoseCanvas2D';
import SpeedChart from '../components/SpeedChart';

enum ConnectionState {
  DISCONNECTED = 'disconnected',
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  RECONNECTING = 'reconnecting',
  ERROR = 'error'
}

interface DisplayIdInfo {
  id: string;
  displayValue: number;
  label: string;
  type: 'jersey' | 'track';
  confidence: number;
  fallbackTrackId: number;
}

export default function VideoAnalysis() {
  const navigate = useNavigate();
  const { taskId } = useParams<{ taskId: string }>();
  const location = useLocation();
  const record = location.state?.record as VideoRecord;

  const [loading, setLoading] = useState(true);
  const [wsConnection, setWsConnection] = useState<WebSocket | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>(ConnectionState.DISCONNECTED);
  const [connectionError, setConnectionError] = useState<string>('');
  const [frameData, setFrameData] = useState<any>(null);
  const [selectedDisplayId, setSelectedDisplayId] = useState<string | null>(null);
  const [retryInfo, setRetryInfo] = useState({ attempts: 0, maxRetries: 5 });
  const [showAllTracks, setShowAllTracks] = useState(false);
  const [videoSize, setVideoSize] = useState({ width: 1920, height: 1080 }); // 默认尺寸

  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const maxReconnectAttempts = 5;

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'completed': return 'green';
      case 'processing': return 'blue';
      case 'failed': return 'red';
      case 'pending': return 'yellow';
      case 'initializing': return 'orange';
      default: return 'gray';
    }
  };

  const connectWebSocket = useCallback((taskId: string) => {
    if (wsConnection) {
      wsConnection.close();
    }

    setConnectionState(ConnectionState.CONNECTING);
    setConnectionError('');

    const API_BASE = import.meta.env.VITE_API_BASE || '';
    const wsUrl = `${API_BASE.replace(/^http/, 'ws')}/ws/pose/${taskId}`;
    
    const ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
      setConnectionState(ConnectionState.CONNECTED);
      setRetryInfo(prev => ({ ...prev, attempts: 0 }));
      setFrameData(null);
    };
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setFrameData(data);
      } catch (error) {
        console.error('WebSocket message parse error:', error);
      }
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setConnectionState(ConnectionState.ERROR);
      setConnectionError('Connection failed');
    };
    
    ws.onclose = (event) => {
      setWsConnection(null);
      
      if (event.code !== 1000 && retryInfo.attempts < maxReconnectAttempts) {
        setConnectionState(ConnectionState.RECONNECTING);
        setRetryInfo(prev => ({ ...prev, attempts: prev.attempts + 1 }));
        
        reconnectTimeoutRef.current = setTimeout(() => {
          connectWebSocket(taskId);
        }, Math.min(1000 * Math.pow(2, retryInfo.attempts), 10000));
      } else {
        setConnectionState(ConnectionState.DISCONNECTED);
        if (event.code !== 1000) {
          setConnectionError('Connection lost');
        }
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

  const handleDisplayIdChange = useCallback((displayId: string | null) => {
    setSelectedDisplayId(displayId);
  }, []);

  const handleDisplayIdsUpdate = useCallback((_displayIds: DisplayIdInfo[]) => {
  }, []);

  useEffect(() => {
    if (taskId) {
      connectWebSocket(taskId);
      setLoading(false);
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
      <Group justify="space-between" align="center" mb="xl">
        <Group>
          <Button 
            variant="outline" 
            onClick={() => navigate('/history')} 
            leftSection={<ArrowLeft size={16} />}
          >
            Back
          </Button>
          <Title order={2}>Video Analysis: {record.filename}</Title>
          <Badge color={getStatusColor(record.status)} size="lg">
            {record.status}
          </Badge>
        </Group>
      </Group>

      {loading ? (
        <Center h={400}>
          <Loader size="xl" />
        </Center>
      ) : (
        <Stack gap="xl">
          {/* Video Player Section */}
          <Card withBorder p="lg">
            <Stack gap="md">
              <Group justify="space-between" align="center">
                <Text fw={600} size="lg">📹 Processed Video</Text>
                <Badge variant="outline" size="lg">Analysis Result</Badge>
              </Group>
              <div style={{ width: '100%', display: 'flex', justifyContent: 'center' }}>
                <video
                  src={record.output_video_url}
                  controls
                  onLoadedMetadata={(e) => {
                    const video = e.target as HTMLVideoElement;
                    setVideoSize({ 
                      width: video.videoWidth, 
                      height: video.videoHeight 
                    });
                    console.log('Video size:', video.videoWidth, video.videoHeight);
                  }}
                  style={{ 
                    width: '100%', 
                    maxWidth: '1000px',
                    height: 'auto',
                    backgroundColor: '#000',
                    borderRadius: '8px'
                  }}
                />
              </div>
            </Stack>
          </Card>

          {/* 2D Pose Visualization */}
          <Card withBorder p="lg">
            <Stack gap="md">
              <Group justify="space-between" align="center">
                <Text fw={600} size="lg">🎯 2D Pose Visualization</Text>
                <Badge variant="outline" size="lg">WebSocket</Badge>
              </Group>
              <div style={{ width: '100%', display: 'flex', justifyContent: 'center' }}>
                <VideoLikePoseCanvas2D
                  frameData={frameData}
                  connectionState={connectionState}
                  connectionError={connectionError}
                  retryInfo={retryInfo}
                  onManualReconnect={handleManualReconnect}
                  width={1000}
                  height={600}
                  videoWidth={videoSize.width}
                  videoHeight={videoSize.height}
                  selectedDisplayId={selectedDisplayId}
                  onDisplayIdsUpdate={handleDisplayIdsUpdate}
                  showSkeleton
                  showJoints
                  showBBoxes
                  targetFps={30}
                  bufferSize={60}
                />
              </div>
            </Stack>
          </Card>

          {/* Speed Chart */}
          <Card withBorder p="lg">
            <Stack gap="md">
              <Group justify="space-between" align="center">
                <Text fw={600} size="lg">📊 Speed Chart</Text>
                <Badge variant="outline" size="lg">Real-time</Badge>
              </Group>
              <SpeedChart
                frameData={frameData}
                connectionState={connectionState}
                connectionError={connectionError}
                retryInfo={retryInfo}
                onManualReconnect={handleManualReconnect}
                selectedDisplayId={selectedDisplayId}
                onDisplayIdChange={handleDisplayIdChange}
                showAllTracks={showAllTracks}
                onShowAllTracksChange={setShowAllTracks}
                height={400}
                maxDataPoints={500}
                smoothingFactor={0.8}
                enableSmoothing={true}
              />
            </Stack>
          </Card>
        </Stack>
      )}
    </Container>
  );
}