import { useEffect, useState } from 'react';
import { Card, Grid, Group, Text, Button, Stack } from '@mantine/core';
import { getStreams, stopStream } from '@/api';

export default function Streams() {
  const [data, setData] = useState<{ active_streams: any[]; count: number } | null>(null);
  const refresh = () => getStreams().then(setData).catch(() => {});

  useEffect(() => { refresh(); }, []);

  return (
    <Stack>
      <Group justify="space-between">
        <Text fw={600}>活跃 Streams ({data?.count ?? 0})</Text>
        <Button onClick={refresh} variant="light">刷新</Button>
      </Group>
      <Grid>
        {(data?.active_streams ?? []).map((s: any, idx) => (
          <Grid.Col key={idx} span={{ base: 12, md: 6, lg: 4 }}>
            <Card withBorder>
              <Text size="sm">{JSON.stringify(s)}</Text>
              {s.task_id && (
                <Button mt="sm" color="red" variant="light" onClick={() => stopStream(s.task_id).then(refresh)}>停止</Button>
              )}
            </Card>
          </Grid.Col>
        ))}
      </Grid>
    </Stack>
  );
}


