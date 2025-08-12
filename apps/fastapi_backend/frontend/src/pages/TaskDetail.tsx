import {useEffect, useMemo, useRef, useState} from 'react';
import {useParams} from 'react-router-dom';
import {Badge, Card, Grid, Group, Stack, Switch, Text, TextInput, Title} from '@mantine/core';
import {getAnnotationRtsp, getPipelineStatus, getTaskStatus} from '@/api';
import MediaPlayer from '@/components/MediaPlayer';

export default function TaskDetail() {
    const {taskId = ''} = useParams();
    const [status, setStatus] = useState<any>(null);
    const [pipeline, setPipeline] = useState<any>(null);
    const [rtsp, setRtsp] = useState<string>('');
    const [testUrl, setTestUrl] = useState('');
    const wsRef = useRef<WebSocket | null>(null);

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
        getAnnotationRtsp(taskId).then((r) => setRtsp(r.processed_rtsp_url)).catch(() => {
        });
    }, [taskId]);

    const wsUrl = useMemo(() => {
        const loc = window.location;
        const proto = loc.protocol === 'https:' ? 'wss' : 'ws';
        return `${proto}://${loc.host}/ws/pose/${taskId}`;
    }, [taskId]);

    useEffect(() => {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;
        ws.onopen = () => console.log('WS connected');
        ws.onmessage = (e) => console.debug('WS', e.data);
        ws.onerror = () => console.warn('WS error');
        ws.onclose = () => console.log('WS closed');
        return () => ws.close();
    }, [wsUrl]);

    return (
        <Stack>
            <Group justify="space-between" align="center">
                <Title order={3}>task {taskId}</Title>
                <Group>
                    <Switch label="detection"/>
                    <Switch label="pose"/>
                    <Switch label="ID"/>
                </Group>
            </Group>
            <Grid>
                <Grid.Col span={{base: 12, lg: 8}}>
                    <Card withBorder>
                        <Stack>
                            <Text size="sm">original RTSP URL: {rtsp || 'not available'}</Text>
                            <TextInput placeholder="test url" value={testUrl}
                                       onChange={(e) => setTestUrl(e.currentTarget.value)}/>
                            <MediaPlayer path={(rtsp || '').replace('rtsp://localhost:8554/', '') || testUrl || ''}/>
                        </Stack>
                    </Card>
                </Grid.Col>
                <Grid.Col span={{base: 12, lg: 4}}>
                    <Stack>
                        <Card withBorder>
                            <Group justify="space-between" align="center">
                                <Text fw={600}>Task Status</Text>
                                {status?.status && <Badge
                                    color={status?.status === 'completed' ? 'green' : 'yellow'}>{status?.status}</Badge>}
                            </Group>
                            <Text size="sm"
                                  mt="xs">任务：{status?.status} {status?.progress ? `(${status.progress})` : ''}</Text>
                            <Text size="sm">创建：{status?.created_at}</Text>
                        </Card>
                        <Card withBorder>
                            <Text fw={600}>Pipeline</Text>
                            <Text size="sm">{pipeline ? 'generated' : 'not generated'}</Text>
                        </Card>
                    </Stack>
                </Grid.Col>
            </Grid>
        </Stack>
    );
}


