import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {useParams} from 'react-router-dom';
import {Alert, Badge, Card, Container, Group, SimpleGrid, Stack, Switch, Text, TextInput, Title} from '@mantine/core';
import {getAnnotationRtsp, getPipelineStatus, getTaskStatus} from '@/api';
import MediaPlayer from '@/components/MediaPlayer';
import VideoLikePoseCanvas2D from "@/components/VideoLikePoseCanvas2D";
import TrackSelector from "@/components/TrackSelector";
import SpeedChart from "@/components/SpeedChart";

// WebSocket 连接状态
enum ConnectionState {
    DISCONNECTED = 'disconnected',
    CONNECTING = 'connecting',
    CONNECTED = 'connected',
    RECONNECTING = 'reconnecting',
    ERROR = 'error'
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
    private onStateChange: (state: ConnectionState, error?: string) => void;

    constructor(
        wsUrl: string,
        onMessage: (data: any) => void,
        onStateChange: (state: ConnectionState, error?: string) => void
    ) {
        this.wsUrl = wsUrl;
        this.onMessage = onMessage;
        this.onStateChange = onStateChange;
    }

    connect(): void {
        if (this.ws?.readyState === WebSocket.CONNECTING || this.ws?.readyState === WebSocket.OPEN) {
            return;
        }

        this.isManuallyDisconnected = false;
        const isReconnect = this.retryAttempts > 0;
        this.onStateChange(isReconnect ? ConnectionState.RECONNECTING : ConnectionState.CONNECTING);

        try {
            this.ws = new WebSocket(this.wsUrl);

            this.ws.onopen = () => {
                console.log('Shared WebSocket connected');
                this.retryAttempts = 0;
                this.onStateChange(ConnectionState.CONNECTED);
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
                } else {
                    this.onStateChange(ConnectionState.DISCONNECTED);
                }
            };

            this.ws.onerror = (evt) => {
                console.error('Shared WebSocket error:', evt);
                this.onStateChange(ConnectionState.ERROR, 'Connection failed');
            };

        } catch (error) {
            console.error('Failed to create shared WebSocket:', error);
            this.onStateChange(ConnectionState.ERROR, 'Failed to create connection');
            this.scheduleReconnect();
        }
    }

    private scheduleReconnect(): void {
        if (this.isManuallyDisconnected || this.retryAttempts >= this.maxRetries) {
            this.onStateChange(ConnectionState.ERROR, `Max retries (${this.maxRetries}) reached`);
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

        this.onStateChange(ConnectionState.DISCONNECTED);
    }

    manualReconnect(): void {
        this.retryAttempts = 0;
        this.disconnect();
        setTimeout(() => this.connect(), 100);
    }

    getConnectionState(): ConnectionState {
        if (!this.ws) return ConnectionState.DISCONNECTED;

        switch (this.ws.readyState) {
            case WebSocket.CONNECTING:
                return this.retryAttempts > 0 ? ConnectionState.RECONNECTING : ConnectionState.CONNECTING;
            case WebSocket.OPEN:
                return ConnectionState.CONNECTED;
            case WebSocket.CLOSING:
            case WebSocket.CLOSED:
            default:
                return ConnectionState.DISCONNECTED;
        }
    }

    getRetryInfo(): { attempts: number; maxRetries: number } {
        return {attempts: this.retryAttempts, maxRetries: this.maxRetries};
    }
}

export default function TaskDetail() {
    const {taskId = ''} = useParams();
    const [status, setStatus] = useState<any>(null);
    const [pipeline, setPipeline] = useState<any>(null);
    const [rtsp, setRtsp] = useState<string>('');
    const [testUrl, setTestUrl] = useState('');

    const containerRef = useRef<HTMLDivElement | null>(null);
    const [size, setSize] = useState({w: 1280, h: 720});
    const [videoSize, setVideoSize] = useState({w: 1280, h: 720});

    // Track ID 选择相关状态 - 全局共享状态
    const [selectedTrackId, setSelectedTrackId] = useState<number | null>(null);
    const [availableTrackIds, setAvailableTrackIds] = useState<number[]>([]);
    const [renderMode, setRenderMode] = useState<'all' | 'single'>('single');

    // 速度图表状态
    const [showAllTracksSpeed, setShowAllTracksSpeed] = useState<boolean>(false);

    // 共享WebSocket状态
    const wsManagerRef = useRef<SharedWebSocketManager | null>(null);
    const [connectionState, setConnectionState] = useState<ConnectionState>(ConnectionState.DISCONNECTED);
    const [connectionError, setConnectionError] = useState<string>('');
    const [retryInfo, setRetryInfo] = useState({attempts: 0, maxRetries: 10});

    // WebSocket数据状态
    const [latestFrameData, setLatestFrameData] = useState<any>(null);

    useEffect(() => {
        if (!containerRef.current) return;
        const el = containerRef.current;
        const ro = new ResizeObserver(entries => {
            for (const entry of entries) {
                // 使用固定宽度，更适合dashboard布局
                const cw = Math.max(640, Math.floor(entry.contentRect.width));
                const ch = Math.floor((cw * 9) / 16);
                setSize({w: cw, h: ch});
            }
        });
        ro.observe(el);
        return () => ro.disconnect();
    }, []);

    useEffect(() => {
        let active = true;
        const poll = async () => {
            try {
                const [s, p] = await Promise.all([
                    getTaskStatus(taskId),
                    getPipelineStatus(taskId),
                ]);
                if (!active) return;
                setStatus(s);
                setPipeline(p);
            } catch {
            }
        };
        poll();
        const id = setInterval(poll, 3000);
        return () => {
            active = false;
            clearInterval(id);
        };
    }, [taskId]);

    useEffect(() => {
        getAnnotationRtsp(taskId)
            .then((r) => setRtsp(r.processed_rtsp_url))
            .catch(() => {
            });
    }, [taskId]);

    const wsUrl = useMemo(() => {
        const loc = window.location;
        const proto = loc.protocol === 'https:' ? 'wss' : 'ws';
        return `${proto}://${loc.host}/ws/pose/${taskId}`;
    }, [taskId]);

    // 当模式变化时自动选择合适的Track ID
    useEffect(() => {
        if (renderMode === 'single' && selectedTrackId === null && availableTrackIds.length > 0) {
            setSelectedTrackId(availableTrackIds[0]); // 自动选择第一个
        } else if (renderMode === 'all') {
            setSelectedTrackId(null);
        }
    }, [renderMode, availableTrackIds, selectedTrackId]);

    // 同步速度图表的显示模式
    useEffect(() => {
        setShowAllTracksSpeed(renderMode === 'all');
    }, [renderMode]);

    // WebSocket 消息处理
    const handleWebSocketMessage = useCallback((data: any) => {
        setLatestFrameData(data);
    }, []);

    // WebSocket 状态变化处理
    const handleWebSocketStateChange = useCallback((state: ConnectionState, error?: string) => {
        setConnectionState(state);
        setConnectionError(error || '');

        if (wsManagerRef.current) {
            setRetryInfo(wsManagerRef.current.getRetryInfo());
        }
    }, []);

    // 手动重连
    const manualReconnect = useCallback(() => {
        setLatestFrameData(null);
        wsManagerRef.current?.manualReconnect();
    }, []);

    // 共享WebSocket管理器初始化
    useEffect(() => {
        wsManagerRef.current = new SharedWebSocketManager(
            wsUrl,
            handleWebSocketMessage,
            handleWebSocketStateChange
        );

        wsManagerRef.current.connect();

        return () => {
            wsManagerRef.current?.disconnect();
            wsManagerRef.current = null;
        };
    }, [wsUrl, handleWebSocketMessage, handleWebSocketStateChange]);

    const handleTrackIdsUpdate = (trackIds: number[]) => {
        setAvailableTrackIds(trackIds);

        // 如果当前选择的Track ID不在新列表中，重置选择
        if (selectedTrackId !== null && !trackIds.includes(selectedTrackId)) {
            if (trackIds.length > 0) {
                setSelectedTrackId(trackIds[0]);
            } else {
                setSelectedTrackId(null);
            }
        }
    };

    const effectiveTrackId = renderMode === 'all' ? null : selectedTrackId;

    return (
        <Container size="xl" px="md">
            {/* 页面头部 */}
            <Group justify="space-between" align="center" mb="xl">
                <Title order={2}>Task {taskId} - Dashboard</Title>
                <Group>
                    {status?.status && (
                        <Badge
                            size="lg"
                            color={status?.status === 'completed' ? 'green' : 'yellow'}
                        >
                            {status?.status}
                        </Badge>
                    )}
                    <Group gap="xs">
                        <Switch label="detection"/>
                        <Switch label="pose" defaultChecked/>
                        <Switch label="ID"/>
                    </Group>
                </Group>
            </Group>

            {/* 主要控制面板 */}
            <Card withBorder mb="lg" p="lg">
                <Group justify="space-between" align="center" mb="md">
                    <Text fw={600} size="lg">🎛️ Control Panel</Text>
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
                        availableTrackIds={availableTrackIds}
                        selectedTrackId={selectedTrackId}
                        onTrackIdChange={setSelectedTrackId}
                        showStats={true}
                    />
                )}

                {/* 性能提示 */}
                {renderMode === 'single' && (
                    <Alert color="green" variant="light" mt="md">
                        🚀 Single track mode enabled for better performance
                    </Alert>
                )}
            </Card>

            {/* 主要内容区域 - Dashboard 布局 */}
            <SimpleGrid cols={{base: 1, md: 2}} spacing="lg">
                {/* 左列：视频播放 */}
                <Card withBorder>
                    <Stack gap="sm">
                        <Group justify="space-between" align="center">
                            <Text fw={600}>📹 Processed Video Stream</Text>
                            <Badge variant="outline">RTSP</Badge>
                        </Group>
                        <div style={{width: '100%'}} ref={containerRef}>
                            <MediaPlayer
                                path={(rtsp || '').replace('rtsp://localhost:8554/', '') || testUrl || ''}
                                onSizeReady={(w, h) => {
                                    console.log('Video size:', w, h);
                                    setVideoSize({w, h});
                                    // 使用容器宽度
                                    const containerWidth = Math.max(480, Math.floor(containerRef.current?.clientWidth || 640));
                                    const containerHeight = Math.floor((containerWidth * 9) / 16);
                                    setSize({w: containerWidth, h: containerHeight});
                                }}
                            />

                        </div>
                        <Group justify="space-between" align="center">
                            <Text fw={600}>📹 Processed Video Stream</Text>
                            <Badge variant="outline">RTSP</Badge>
                        </Group>
                        <Text size="sm" c="dimmed">RTSP: {rtsp || 'not available'}</Text>
                        <TextInput
                            placeholder="test url (optional)"
                            value={testUrl}
                            onChange={(e) => setTestUrl(e.currentTarget.value)}
                            size="sm"
                        />
                    </Stack>
                </Card>

                {/* 右列：Pose Canvas */}
                <Card withBorder>
                    <Stack gap="sm">
                        <Group justify="space-between" align="center">
                            <Text fw={600}>🎯 Pose Tracking</Text>
                            <Badge variant="outline">WebSocket</Badge>
                        </Group>
                        <div style={{width: '100%', height: size.h}}>
                            <VideoLikePoseCanvas2D
                                frameData={latestFrameData}
                                connectionState={connectionState}
                                connectionError={connectionError}
                                retryInfo={retryInfo}
                                onManualReconnect={manualReconnect}
                                width={size.w}
                                height={size.h}
                                videoWidth={videoSize.w}
                                videoHeight={videoSize.h}
                                selectedTrackId={effectiveTrackId}
                                showSkeleton
                                showJoints
                                showBBoxes
                                showDebug={false} // 在dashboard中关闭debug
                                targetFps={25}
                                bufferSize={30}
                                onTrackIdsUpdate={handleTrackIdsUpdate}
                            />
                        </div>
                    </Stack>
                </Card>
            </SimpleGrid>

            {/* 底部：速度图表 */}
            <Card withBorder mt="lg">
                <SpeedChart
                    frameData={latestFrameData}
                    connectionState={connectionState}
                    connectionError={connectionError}
                    retryInfo={retryInfo}
                    onManualReconnect={manualReconnect}
                    selectedTrackId={selectedTrackId}
                    onTrackIdChange={setSelectedTrackId}
                    showAllTracks={showAllTracksSpeed}
                    onShowAllTracksChange={(showAll) => {
                        setShowAllTracksSpeed(showAll);
                        setRenderMode(showAll ? 'all' : 'single');
                    }}
                    maxDataPoints={150}
                    height={350}
                />
            </Card>

            {/* 状态信息 */}
            <Group gap="md" justify="center" mt="lg" p="md" style={{
                backgroundColor: '#f8f9fa',
                borderRadius: '8px'
            }}>
                <Text size="sm" c="dimmed">
                    📊 Mode: {renderMode === 'single' ? `Single (Track ${effectiveTrackId ?? 'None'})` : 'All Tracks'}
                </Text>
                <Text size="sm" c="dimmed">
                    👥 Available tracks: {availableTrackIds.length}
                </Text>
                <Text size="sm" c="dimmed">
                    📐 Canvas: {size.w}×{size.h}
                </Text>
                <Text size="sm" c="dimmed">
                    🎥 Video: {videoSize.w}×{videoSize.h}
                </Text>
            </Group>
        </Container>
    );
}