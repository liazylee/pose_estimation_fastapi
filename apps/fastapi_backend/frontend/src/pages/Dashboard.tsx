import { Card, Grid, Group, Text, Button, Skeleton } from '@mantine/core';
import { useEffect, useState } from 'react';
import { getHealth, getAIHealth, getStreams } from '@/api';
import type { HealthResponse, StreamsResponse } from '@/api/types';
import { Link } from 'react-router-dom';

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [aiHealth, setAIHealth] = useState<any | null>(null);
  const [streams, setStreams] = useState<StreamsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    Promise.all([getHealth(), getAIHealth(), getStreams()])
      .then(([h, a, s]) => { if (!mounted) return; setHealth(h); setAIHealth(a); setStreams(s); })
      .finally(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, []);

  return (
    <Grid>
      <Grid.Col span={{ base: 12, md: 6, lg: 3 }}>
        <StatusCard title="后端健康" status={health?.status} loading={loading} />
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 6, lg: 3 }}>
        <StatusCard title="AI 服务健康" status={aiHealth?.overall_healthy ? 'healthy' : 'degraded'} loading={loading} />
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 6, lg: 3 }}>
        <StatusCard title="活跃 Streams" status={String(streams?.count ?? 0)} loading={loading} />
      </Grid.Col>
      <Grid.Col span={{ base: 12 }}>
        <Card withBorder>
          <Group justify="space-between">
            <Text>快捷入口</Text>
            <Group>
              <Button component={Link} to="/upload">上传</Button>
              <Button component={Link} to="/streams" variant="light">查看 Streams</Button>
              <Button component={Link} to="/dashboard" variant="light">后端Dashboard</Button>
            </Group>
          </Group>
        </Card>
      </Grid.Col>
    </Grid>
  );
}

function StatusCard({ title, status, loading }: { title: string; status?: string; loading: boolean }) {
  const color = status === 'healthy' ? 'green' : status ? 'yellow' : 'gray';
  return (
    <Card withBorder>
      <Text size="sm" c="dimmed">{title}</Text>
      {loading ? (
        <Skeleton h={24} mt="sm" />
      ) : (
        <Text fw={700} c={color}>{status ?? 'N/A'}</Text>
      )}
    </Card>
  );
}


