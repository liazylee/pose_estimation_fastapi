import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {useParams} from 'react-router-dom';
import {Alert, Badge, Card, Container, Group, SimpleGrid, Stack, Switch, Text, TextInput, Title} from '@mantine/core';
import {getAnnotationRtsp, getPipelineStatus, getTaskStatus} from '@/api';
import MediaPlayer from '@/components/MediaPlayer';
import VideoLikePoseCanvas2D from "@/components/VideoLikePoseCanvas2D";
import TrackSelector from "@/components/TrackSelector";
import SpeedChart from "@/components/SpeedChart";

interface DisplayIdInfo {
    id: string;
    displayValue: number;
    label: string;
    type: 'jersey' | 'track';
    confidence: number;
    fallbackTrackId: number;
}

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

    // Display ID 选择相关状态 - 全局共享状态
    const [selectedDisplayId, setSelectedDisplayId] = useState<string | null>(null);
    const [availableDisplayIds, setAvailableDisplayIds] = useState<DisplayIdInfo[]>([]);
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
                // 垂直布局下使用更大的宽度，充分利用空间
                const cw = Math.max(900, Math.floor(entry.contentRect.width * 0.9));
                const ch = Math.floor((cw * 9) / 16);
                setSize({w: cw, h: ch});
            }
        });
        ro.observe(el);
        return () => ro.disconnect();
    }, []);

    useEffect(() => {
        // 只在页面初始化时获取一次状态，不再轮询
        const fetchInitialStatus = async () => {
            try {
                const [s, p] = await Promise.all([
                    getTaskStatus(taskId),
                    getPipelineStatus(taskId),
                ]);
                setStatus(s);
                setPipeline(p);
            } catch (error) {
                console.error('Failed to fetch initial status:', error);
            }
        };
        
        fetchInitialStatus();
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

    // 当模式变化时自动选择合适的Display ID
    useEffect(() => {
        if (renderMode === 'single' && selectedDisplayId === null && availableDisplayIds.length > 0) {
            setSelectedDisplayId(availableDisplayIds[0].id); // 自动选择第一个
        } else if (renderMode === 'all') {
            setSelectedDisplayId(null);
        }
    }, [renderMode, availableDisplayIds, selectedDisplayId]);

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
                        availableDisplayIds={availableDisplayIds}
                        selectedDisplayId={selectedDisplayId}
                        onDisplayIdChange={setSelectedDisplayId}
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

            {/* 主要内容区域 - 垂直堆叠布局 */}
            <Stack gap="xl">
                {/* 上面：处理后的视频 */}
                <Card withBorder p="lg">
                    <Stack gap="md">
                        <Group justify="space-between" align="center">
                            <Text fw={600} size="lg">📹 Processed Video Stream</Text>
                            <Badge variant="outline" size="lg">RTSP</Badge>
                        </Group>
                        <div style={{width: '100%', display: 'flex', justifyContent: 'center'}} ref={containerRef}>
                            <MediaPlayer
                                path={(rtsp || '').replace('rtsp://localhost:8554/', '') || testUrl || ''}
                                onSizeReady={(w, h) => {
                                    console.log('Video size:', w, h);
                                    setVideoSize({w, h});
                                    // 垂直布局下使用全宽度，提供更好的观看体验
                                    const containerWidth = Math.max(1000, Math.floor(containerRef.current?.clientWidth * 0.85 || 1200));
                                    const containerHeight = Math.floor((containerWidth * 9) / 16);
                                    setSize({w: containerWidth, h: containerHeight});
                                }}
                            />
                        </div>
                        <Group justify="space-between" align="center" mt="xs">
                            <Text size="sm" c="dimmed">RTSP: {rtsp || 'not available'}</Text>
                            <TextInput
                                placeholder="test url (optional)"
                                value={testUrl}
                                onChange={(e) => setTestUrl(e.currentTarget.value)}
                                size="sm"
                                style={{maxWidth: '300px'}}
                            />
                        </Group>
                    </Stack>
                </Card>

                {/* 中间：Pose Canvas */}
                <Card withBorder p="lg">
                    <Stack gap="md">
                        <Group justify="space-between" align="center">
                            <Text fw={600} size="lg">🎯 Pose Tracking</Text>
                            <Badge variant="outline" size="lg">WebSocket</Badge>
                        </Group>
                        <div style={{width: '100%', display: 'flex', justifyContent: 'center'}}>
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
                                selectedDisplayId={effectiveDisplayId}
                                showSkeleton
                                showJoints
                                showBBoxes
                                showDebug={false}
                                targetFps={25}
                                bufferSize={30}
                                onDisplayIdsUpdate={handleDisplayIdsUpdate}
                                jerseyConfidenceThreshold={0.7}
                            />
                        </div>
                    </Stack>
                </Card>

                {/* 下面：速度图表 */}
                <Card withBorder p="lg">
                    <Stack gap="md">
                        <Group justify="space-between" align="center">
                            <Text fw={600} size="lg">📊 Speed Chart</Text>
                            <Badge variant="outline" size="lg">Real-time</Badge>
                        </Group>
                        <SpeedChart
                            frameData={latestFrameData}
                            connectionState={connectionState}
                            connectionError={connectionError}
                            retryInfo={retryInfo}
                            onManualReconnect={manualReconnect}
                            selectedDisplayId={selectedDisplayId}
                            onDisplayIdChange={setSelectedDisplayId}
                            showAllTracks={showAllTracksSpeed}
                            onShowAllTracksChange={(showAll) => {
                                setShowAllTracksSpeed(showAll);
                                setRenderMode(showAll ? 'all' : 'single');
                            }}
                            maxDataPoints={150}
                            height={300}
                            jerseyConfidenceThreshold={0.7}
                        />
                    </Stack>
                </Card>
            </Stack>

            {/* 状态信息 */}
            <Group gap="md" justify="center" mt="lg" p="md" style={{
                backgroundColor: '#f8f9fa',
                borderRadius: '8px'
            }}>
                <Text size="sm" c="dimmed">
                    📊 Mode: {renderMode === 'single' ? 
                        `Single (${effectiveDisplayId ? 
                            availableDisplayIds.find(d => d.id === effectiveDisplayId)?.label || 'Unknown'
                            : 'None'})` 
                        : 'All Players'}
                </Text>
                <Text size="sm" c="dimmed">
                    👥 Available players: {availableDisplayIds.length} ({availableDisplayIds.filter(d => d.type === 'jersey').length} jerseys, {availableDisplayIds.filter(d => d.type === 'track').length} tracks)
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