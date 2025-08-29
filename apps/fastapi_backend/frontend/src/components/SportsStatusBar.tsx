// SportsStatusBar.tsx - Sports-themed status bar with real-time metrics
import React from 'react';
import { Badge, Group, Text, Progress, Tooltip } from '@mantine/core';
import '../styles/sports-theme.css';

interface SportsStatusBarProps {
    connectionState: 'connected' | 'connecting' | 'disconnected' | 'reconnecting' | 'error';
    frameRate: number;
    bufferHealth: number;
    totalPlayers: number;
    jerseyDetections: number;
    latency?: number;
}

export default function SportsStatusBar({
    connectionState,
    frameRate,
    bufferHealth,
    totalPlayers,
    jerseyDetections,
    latency = 0
}: SportsStatusBarProps) {
    const getConnectionStatus = () => {
        switch (connectionState) {
            case 'connected':
                return { color: 'green', icon: '🟢', text: 'LIVE' };
            case 'connecting':
                return { color: 'yellow', icon: '🟡', text: 'CONNECTING' };
            case 'reconnecting':
                return { color: 'orange', icon: '🟠', text: 'RECONNECTING' };
            case 'error':
                return { color: 'red', icon: '🔴', text: 'ERROR' };
            default:
                return { color: 'gray', icon: '⚫', text: 'OFFLINE' };
        }
    };

    const getPerformanceColor = (value: number, thresholds: [number, number]) => {
        if (value >= thresholds[1]) return 'green';
        if (value >= thresholds[0]) return 'yellow';
        return 'red';
    };

    const status = getConnectionStatus();

    return (
        <div className="sports-dashboard-card" style={{ padding: '12px 16px', marginBottom: '16px' }}>
            <Group justify="space-between" align="center">
                {/* Connection Status */}
                <Group gap="xs">
                    <div className="connection-status">
                        <Badge
                            color={status.color}
                            variant="filled"
                            className={connectionState === 'connected' ? 'live-indicator' : ''}
                            leftSection={status.icon}
                        >
                            {status.text}
                        </Badge>
                    </div>
                    {latency > 0 && (
                        <Text size="xs" c="dimmed">
                            {latency}ms
                        </Text>
                    )}
                </Group>

                {/* Performance Metrics */}
                <Group gap="lg">
                    <Tooltip label="Frames per second">
                        <Group gap="xs">
                            <Text size="sm" fw={600}>FPS:</Text>
                            <Badge
                                color={getPerformanceColor(frameRate, [20, 25])}
                                variant="light"
                            >
                                {frameRate.toFixed(1)}
                            </Badge>
                        </Group>
                    </Tooltip>

                    <Tooltip label="Buffer health percentage">
                        <Group gap="xs">
                            <Text size="sm" fw={600}>Buffer:</Text>
                            <div style={{ width: '60px' }}>
                                <Progress
                                    value={bufferHealth}
                                    color={getPerformanceColor(bufferHealth, [30, 60])}
                                    size="sm"
                                />
                            </div>
                            <Text size="xs" c="dimmed">{bufferHealth.toFixed(0)}%</Text>
                        </Group>
                    </Tooltip>

                    <Tooltip label="Total players detected">
                        <Group gap="xs">
                            <Text size="sm" fw={600}>👥</Text>
                            <Badge color="blue" variant="light">
                                {totalPlayers}
                            </Badge>
                        </Group>
                    </Tooltip>

                    <Tooltip label="Jersey numbers detected">
                        <Group gap="xs">
                            <Text size="sm" fw={600}>🏆</Text>
                            <Badge 
                                color={jerseyDetections > 0 ? 'gold' : 'gray'}
                                variant={jerseyDetections > 0 ? 'filled' : 'light'}
                                className={jerseyDetections > 0 ? 'jersey-badge' : ''}
                            >
                                {jerseyDetections}
                            </Badge>
                        </Group>
                    </Tooltip>
                </Group>

                {/* Detection Rate */}
                <Group gap="xs">
                    <Text size="sm" fw={600}>Detection Rate:</Text>
                    <Text 
                        size="sm" 
                        c={totalPlayers > 0 ? (jerseyDetections / totalPlayers > 0.7 ? 'green' : jerseyDetections / totalPlayers > 0.4 ? 'yellow' : 'red') : 'gray'}
                        fw={600}
                    >
                        {totalPlayers > 0 ? `${Math.round((jerseyDetections / totalPlayers) * 100)}%` : '0%'}
                    </Text>
                </Group>
            </Group>
        </div>
    );
}