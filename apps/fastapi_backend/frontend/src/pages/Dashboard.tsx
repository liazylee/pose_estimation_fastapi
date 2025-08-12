import {Badge, Button, Card, Grid, Group, Skeleton, Stack, Text, Title} from '@mantine/core';
import {useEffect, useState} from 'react';
import {getAIHealth, getHealth, getStreams} from '@/api';
import type {HealthResponse, StreamsResponse} from '@/api/types';
import {Link} from 'react-router-dom';

export default function Dashboard() {
    const [health, setHealth] = useState<HealthResponse | null>(null);
    const [aiHealth, setAIHealth] = useState<any | null>(null);
    const [streams, setStreams] = useState<StreamsResponse | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let mounted = true;
        Promise.all([getHealth(), getAIHealth(), getStreams()])
            .then(([h, a, s]) => {
                if (!mounted) return;
                setHealth(h);
                setAIHealth(a);
                setStreams(s);
            })
            .finally(() => mounted && setLoading(false));
        return () => {
            mounted = false;
        };
    }, []);

    return (
        <Stack>
            <Title order={3}>dashboard</Title>
            <Grid>
                <Grid.Col span={{base: 12, md: 6, lg: 3}}>
                    <StatusCard title="health of backend" status={health?.status} loading={loading}/>
                </Grid.Col>
                <Grid.Col span={{base: 12, md: 6, lg: 3}}>
                    <StatusCard title="AI health" status={aiHealth?.overall_healthy ? 'healthy' : 'degraded'}
                                loading={loading}/>
                </Grid.Col>
                <Grid.Col span={{base: 12, md: 6, lg: 3}}>
                    <StatusCard title="active Streams" status={String(streams?.count ?? 0)} loading={loading}/>
                </Grid.Col>
            </Grid>

            <Card withBorder>
                <Group justify="space-between" align="center">
                    <Group>
                        <Text fw={600}>quick actions</Text>
                        {!loading && (
                            <Badge variant="light" color="gray">{streams?.count ?? 0} streams</Badge>
                        )}
                    </Group>
                    <Group>
                        <Button component={Link} to="/upload">upload</Button>
                        <Button component={Link} to="/streams" variant="light"> Streams</Button>
                        <Button component={Link} to="/dashboard" variant="light">backend Dashboard</Button>
                    </Group>
                </Group>
            </Card>
        </Stack>
    );
}

function StatusCard({title, status, loading}: { title: string; status?: string; loading: boolean }) {
    const color = status === 'healthy' ? 'green' : status ? 'yellow' : 'gray';
    return (
        <Card withBorder>
            <Text size="sm" c="dimmed">{title}</Text>
            {loading ? (
                <Skeleton h={24} mt="sm"/>
            ) : (
                <Text fw={700} c={color}>{status ?? 'N/A'}</Text>
            )}
        </Card>
    );
}


