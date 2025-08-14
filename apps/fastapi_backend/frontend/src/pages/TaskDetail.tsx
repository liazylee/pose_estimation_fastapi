import {useEffect, useMemo, useRef, useState} from 'react';
import {useParams} from 'react-router-dom';
import {Alert, Badge, Card, Group, Stack, Switch, Text, TextInput, Title} from '@mantine/core';
import {getAnnotationRtsp, getPipelineStatus, getTaskStatus} from '@/api';
import MediaPlayer from '@/components/MediaPlayer';
import VideoLikePoseCanvas2D from "@/components/VideoLikePoseCanvas2D";
import TrackSelector from "@/components/TrackSelector";

export default function TaskDetail() {
    const {taskId = ''} = useParams();
    const [status, setStatus] = useState<any>(null);
    const [pipeline, setPipeline] = useState<any>(null);
    const [rtsp, setRtsp] = useState<string>('');
    const [testUrl, setTestUrl] = useState('');

    const containerRef = useRef<HTMLDivElement | null>(null);
    const [size, setSize] = useState({w: 1280, h: 720});

    // 新增：Track ID 选择相关状态
    const [selectedTrackId, setSelectedTrackId] = useState<number | null>(null);
    const [availableTrackIds, setAvailableTrackIds] = useState<number[]>([]);
    const [renderMode, setRenderMode] = useState<'all' | 'single'>('single');

    useEffect(() => {
        if (!containerRef.current) return;
        const el = containerRef.current;
        const ro = new ResizeObserver(entries => {
            for (const entry of entries) {
                const cw = Math.max(320, Math.floor(entry.contentRect.width));
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
        <Stack gap="lg" ref={containerRef}>
            <Group justify="space-between" align="center">
                <Title order={3}>Task {taskId}</Title>
                <Group>
                    <Switch label="detection"/>
                    <Switch label="pose" defaultChecked/>
                    <Switch label="ID"/>
                </Group>
            </Group>

            <Card withBorder>
                <Stack gap="sm">
                    <Group justify="space-between" align="center">
                        <Text fw={600}>Processed Video Stream (AI Annotations)</Text>
                        {status?.status && (
                            <Badge color={status?.status === 'completed' ? 'green' : 'yellow'}>
                                {status?.status}
                            </Badge>
                        )}
                    </Group>
                    <Text size="sm">RTSP: {rtsp || 'not available'}</Text>
                    <TextInput
                        placeholder="test url"
                        value={testUrl}
                        onChange={(e) => setTestUrl(e.currentTarget.value)}
                    />
                    <div style={{width: size.w, height: size.h}}>
                        <MediaPlayer
                            path={(rtsp || '').replace('rtsp://localhost:8554/', '') || testUrl || ''}
                            onSizeReady={(w, h) => {
                                console.log(w, h);
                                setSize({w, h});
                            }}
                        />
                    </div>
                </Stack>
            </Card>

            <Card withBorder>
                <Stack gap="md">
                    <Group justify="space-between" align="center">
                        <Text fw={600}>Pose Render (WebSocket → Canvas)</Text>
                        <Group>
                            <Switch
                                label="Single Track Mode"
                                checked={renderMode === 'single'}
                                onChange={(e) => setRenderMode(e.currentTarget.checked ? 'single' : 'all')}
                                color="green"
                            />
                        </Group>
                    </Group>

                    {/* 性能提示 */}
                    {renderMode === 'single' && (
                        <Alert color="green" variant="light">
                            🚀 Single track mode enabled for better performance
                        </Alert>
                    )}

                    {/* Track 选择器 */}
                    {renderMode === 'single' && (
                        <TrackSelector
                            availableTrackIds={availableTrackIds}
                            selectedTrackId={selectedTrackId}
                            onTrackIdChange={setSelectedTrackId}
                            showStats={true}
                        />
                    )}

                    {/* Canvas 渲染区域 */}
                    <div style={{width: size.w, height: size.h}}>
                        <VideoLikePoseCanvas2D
                            wsUrl={wsUrl}
                            width={size.w}
                            height={size.h}
                            selectedTrackId={effectiveTrackId}
                            showSkeleton
                            showJoints
                            showBBoxes
                            showDebug={true}
                            targetFps={25} // 25fps播放
                            bufferSize={30} // 30帧缓冲
                            onTrackIdsUpdate={handleTrackIdsUpdate}
                        />
                    </div>

                    {/* 状态信息 */}
                    <Group gap="md" justify="space-between">
                        <Text size="sm" c="dimmed">
                            Mode: {renderMode === 'single' ? `Single (Track ${effectiveTrackId ?? 'None'})` : 'All Tracks'}
                        </Text>
                        <Text size="sm" c="dimmed">
                            Available tracks: {availableTrackIds.length}
                        </Text>
                    </Group>
                </Stack>
            </Card>
        </Stack>
    );
}