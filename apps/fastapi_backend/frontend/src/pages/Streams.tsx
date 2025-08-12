import {useEffect, useState} from 'react';
import {Button, Card, Center, Grid, Group, Stack, Text, Title} from '@mantine/core';
import {getStreams, stopStream} from '@/api';

export default function Streams() {
    const [data, setData] = useState<{ active_streams: any[]; count: number } | null>(null);
    const refresh = () => getStreams().then(setData).catch(() => {
    });

    useEffect(() => {
        refresh();
    }, []);

    const hasStreams = (data?.active_streams?.length ?? 0) > 0;

    return (
        <Stack>
            <Group justify="space-between">
                <Title order={3}>active Streams</Title>
                <Button onClick={refresh} variant="light">refresh</Button>
            </Group>
            {!hasStreams ? (
                <Card withBorder>
                    <Center>
                        <Text c="dimmed"> No active streams found</Text>
                    </Center>
                </Card>
            ) : (
                <Grid>
                    {(data?.active_streams ?? []).map((s: any, idx) => (
                        <Grid.Col key={idx} span={{base: 12, md: 6, lg: 4}}>
                            <Card withBorder>
                                <Text size="sm" style={{whiteSpace: 'pre-wrap'}}>{JSON.stringify(s, null, 2)}</Text>
                                {s.task_id && (
                                    <Button mt="sm" color="red" variant="light"
                                            onClick={() => stopStream(s.task_id).then(refresh)}>停止</Button>
                                )}
                            </Card>
                        </Grid.Col>
                    ))}
                </Grid>
            )}
        </Stack>
    );
}


