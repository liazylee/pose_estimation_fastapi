import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {useParams} from 'react-router-dom';
import {Alert, Card, Container, Group, Stack, Switch, Text, Title} from '@mantine/core';
import * as api from '@/api';
import MediaPlayer from '@/components/MediaPlayer';
import VideoLikePoseCanvas2D from "@/components/VideoLikePoseCanvas2D";
import TrackSelector from "@/components/TrackSelector";
import SpeedChart from "@/components/SpeedChart";
import { useGlobalStore } from '@/store/global';

interface DisplayIdInfo {
    id: string;
    displayValue: number;
    label: string;
    type: 'jersey' | 'track';
    confidence: number;
    fallbackTrackId: number;
}

// 共享的WebSocket管理器
class SharedWebSocketManager {
    private wsUrl: string;
    private ws: WebSocket | null = null;
    private retryAttempts = 0;
    private maxRetries = 10;
    private baseDelay = 1000;
    private maxDelay = 30000;
    private retryTimeout: NodeJS.Timeout | null = null;
    private isManuallyDisconnected = false;

    private onMessage: (data: any) => void;

    constructor(
        wsUrl: string,
        onMessage: (data: any) => void,
    ) {
        this.wsUrl = wsUrl;
        this.onMessage = onMessage;
    }

    connect(): void {
        if (this.ws?.readyState === WebSocket.CONNECTING || this.ws?.readyState === WebSocket.OPEN) {
            return;
        }

        this.isManuallyDisconnected = false;

        try {
            this.ws = new WebSocket(this.wsUrl);

            this.ws.onopen = () => {
                console.log('Shared WebSocket connected');
                this.retryAttempts = 0;
            };

            this.ws.onmessage = (evt) => {
                try {
                    const data = JSON.parse(evt.data);
                    this.onMessage(data);
                } catch (e) {
                    console.warn("Failed to parse WebSocket message:", e);
                }
            };

            this.ws.onclose = (evt) => {
                console.log('Shared WebSocket closed:', evt.code, evt.reason);
                this.ws = null;

                if (!this.isManuallyDisconnected) {
                    this.scheduleReconnect();
                }
            };

            this.ws.onerror = (evt) => {
                console.error('Shared WebSocket error:', evt);
            };
        } catch (error) {
            console.error('Failed to create shared WebSocket:', error);
            this.scheduleReconnect();
        }
    }

    private scheduleReconnect(): void {
        if (this.isManuallyDisconnected || this.retryAttempts >= this.maxRetries) {
            return;
        }

        this.retryAttempts++;

        const delay = Math.min(
            this.baseDelay * Math.pow(2, this.retryAttempts - 1),
            this.maxDelay
        );

        console.log(`Scheduling shared WebSocket reconnect attempt ${this.retryAttempts}/${this.maxRetries} in ${delay}ms`);

        this.retryTimeout = setTimeout(() => {
            this.connect();
        }, delay);
    }

    disconnect(): void {
        this.isManuallyDisconnected = true;

        if (this.retryTimeout) {
            clearTimeout(this.retryTimeout);
            this.retryTimeout = null;
        }

        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    manualReconnect(): void {
        this.retryAttempts = 0;
        this.disconnect();
        setTimeout(() => this.connect(), 100);
    }
}

export default function TaskDetail() {
    const isM3u8Ready = useGlobalStore(s => s.isM3u8Ready);
    const {taskId = ''} = useParams();

    const [rtsp, setRtsp] = useState<string>('');

    // Display ID 选择相关状态 - 全局共享状态
    const [selectedDisplayId, setSelectedDisplayId] = useState<string | null>(null);
    const [availableDisplayIds, setAvailableDisplayIds] = useState<DisplayIdInfo[]>([]);
    const [renderMode, setRenderMode] = useState<'all' | 'single'>('single');

    // 共享WebSocket状态
    const wsManagerRef = useRef<SharedWebSocketManager | null>(null);

    // WebSocket数据状态
    const [latestFrameData, setLatestFrameData] = useState<any>(null);

    useEffect(() => {
        api.getAnnotationRtsp(taskId)
            .then((r) => setRtsp(r.processed_rtsp_url))
            .catch(() => {});
    }, [taskId]);

    const wsUrl = useMemo(() => {
        const loc = window.location;
        const proto = loc.protocol === 'https:' ? 'wss' : 'ws';
        return `${proto}://${loc.host}/ws/pose/${taskId}`;
    }, [taskId]);

    // 当模式变化时自动选择合适的Display ID
    useEffect(() => {
        if (renderMode === 'single' && selectedDisplayId === null && availableDisplayIds.length > 0) {
            setSelectedDisplayId(availableDisplayIds[0].id); // 自动选择第一个
        } else if (renderMode === 'all') {
            setSelectedDisplayId(null);
        }
    }, [renderMode, availableDisplayIds, selectedDisplayId]);

    // 手动重连
    const manualReconnect = useCallback(() => {
        setLatestFrameData(null);
        wsManagerRef.current?.manualReconnect();
    }, []);

    // 共享WebSocket管理器初始化
    useEffect(() => {
        if (!isM3u8Ready) return;
        if(!wsUrl) return;

        wsManagerRef.current = new SharedWebSocketManager(
            wsUrl,
            (data) => setLatestFrameData(data)
        );
        wsManagerRef.current.connect();

        return () => {
            wsManagerRef.current?.disconnect();
            wsManagerRef.current = null;
        };
    }, [wsUrl, isM3u8Ready]);

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

    const effectiveDisplayId = renderMode === 'all' ? null : selectedDisplayId;

    return (
        <Container size="xl" px="md">
            {/* 页面头部 */}
            <Group justify="space-between" align="center" mb="xl">
                <Title order={2}>Task {taskId} - Dashboard</Title>
                <Group gap="xs">
                    <Switch label="detection"/>
                    <Switch label="pose" defaultChecked/>
                    <Switch label="ID"/>
                </Group>
            </Group>

            {/* 主要内容区域 - 垂直堆叠布局 */}
            <Stack gap="xl">
                {/* 上面：处理后的视频 */}
                <Card withBorder p="lg">
                    <Stack gap="md">
                        <Text fw={600} size="lg">📹 Processed Video Stream</Text>
                        <MediaPlayer path={(rtsp || '').replace('rtsp://localhost:8554/', '') || ''} />
                        <Text size="sm" c="dimmed">RTSP: {rtsp || 'not available'}</Text>
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
                            frameData={latestFrameData}
                            onManualReconnect={manualReconnect}
                            selectedDisplayId={effectiveDisplayId}
                            onDisplayIdsUpdate={handleDisplayIdsUpdate}
                        />

                        {/* 下面：速度图表 */}
                        <Text fw={600} size="lg" mt="xl">📊 Speed Chart</Text>
                        <SpeedChart
                            frameData={latestFrameData}
                            selectedDisplayId={selectedDisplayId}
                            showAllTracks={renderMode === 'all'}
                        />
                    </Stack>
                </Card>
            </Stack>
        </Container>
    );
}
