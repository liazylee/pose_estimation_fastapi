import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Card, Group, Text, Stack, Switch, Grid, TextInput } from '@mantine/core';
import { getAnnotationRtsp, getPipelineStatus, getTaskStatus } from '@/api';
import MediaPlayer from '@/components/MediaPlayer';

export default function TaskDetail() {
  const { taskId = '' } = useParams();
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
        setStatus(s); setPipeline(p);
      } catch {}
    };
    poll();
    const id = setInterval(poll, 3000);
    return () => { active = false; clearInterval(id); };
  }, [taskId]);

  useEffect(() => {
    getAnnotationRtsp(taskId).then((r) => setRtsp(r.processed_rtsp_url)).catch(() => {});
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
    <Grid>
      <Grid.Col span={{ base: 12, lg: 8 }}>
        <Card withBorder>
          <Group justify="space-between">
            <Text fw={600}>任务 {taskId}</Text>
            <Group>
              <Switch label="框" />
              <Switch label="骨架" />
              <Switch label="ID" />
            </Group>
          </Group>
          <Stack mt="md">
            <Text size="sm">播放地址（优先注释RTSP）：{rtsp || '无'}</Text>
            <TextInput placeholder="测试流URL（占位）" value={testUrl} onChange={(e) => setTestUrl(e.currentTarget.value)} />
            <MediaPlayer path={(rtsp || '').replace('rtsp://localhost:8554/', '') || testUrl || ''} />
          </Stack>
        </Card>
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 4 }}>
        <Stack>
          <Card withBorder>
            <Text fw={600}>状态</Text>
            <Text size="sm">任务：{status?.status} {status?.progress ? `(${status.progress})` : ''}</Text>
            <Text size="sm">创建：{status?.created_at}</Text>
          </Card>
          <Card withBorder>
            <Text fw={600}>Pipeline</Text>
            <Text size="sm">{pipeline ? '已获取' : '加载中...'}</Text>
          </Card>
        </Stack>
      </Grid.Col>
    </Grid>
  );
}


