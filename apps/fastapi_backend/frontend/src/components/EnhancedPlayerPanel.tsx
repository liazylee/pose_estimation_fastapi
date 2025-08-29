// EnhancedPlayerPanel.tsx - Enhanced player information panel
import React from 'react';
import { Badge, Card, Group, Stack, Text, Progress, ActionIcon, Tooltip } from '@mantine/core';
import { IconEye, IconEyeOff, IconTarget } from '@tabler/icons-react';
import '../styles/sports-theme.css';

interface PlayerInfo {
    id: string;
    displayValue: number;
    label: string;
    type: 'jersey' | 'track';
    confidence: number;
    fallbackTrackId: number;
    currentSpeed?: number;
    maxSpeed?: number;
    timeOnScreen?: number;
    lastSeen?: number;
}

interface EnhancedPlayerPanelProps {
    players: PlayerInfo[];
    selectedPlayerId: string | null;
    onPlayerSelect: (playerId: string | null) => void;
    showAll: boolean;
    onShowAllChange: (showAll: boolean) => void;
}

export default function EnhancedPlayerPanel({
    players,
    selectedPlayerId,
    onPlayerSelect,
    showAll,
    onShowAllChange
}: EnhancedPlayerPanelProps) {
    const getConfidenceColor = (confidence: number) => {
        if (confidence >= 0.8) return 'green';
        if (confidence >= 0.6) return 'yellow';
        return 'red';
    };

    const getSpeedColor = (speed: number) => {
        if (speed >= 20) return 'red';
        if (speed >= 15) return 'orange';
        if (speed >= 10) return 'yellow';
        return 'green';
    };

    const formatTime = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    const jerseyPlayers = players.filter(p => p.type === 'jersey');
    const trackPlayers = players.filter(p => p.type === 'track');

    return (
        <div className="player-selector">
            <Stack gap="md">
                {/* Header with controls */}
                <Group justify="space-between" align="center">
                    <Text fw={600} size="lg">🏃‍♂️ Player Panel</Text>
                    <Group gap="xs">
                        <Tooltip label={showAll ? "Show selected player only" : "Show all players"}>
                            <ActionIcon
                                variant={showAll ? "filled" : "light"}
                                color="blue"
                                onClick={() => onShowAllChange(!showAll)}
                                className="sports-button-primary"
                            >
                                {showAll ? <IconEye size={16} /> : <IconEyeOff size={16} />}
                            </ActionIcon>
                        </Tooltip>
                        {selectedPlayerId && (
                            <Tooltip label="Clear selection">
                                <ActionIcon
                                    variant="light"
                                    color="gray"
                                    onClick={() => onPlayerSelect(null)}
                                >
                                    <IconTarget size={16} />
                                </ActionIcon>
                            </Tooltip>
                        )}
                    </Group>
                </Group>

                {/* Jersey Players Section */}
                {jerseyPlayers.length > 0 && (
                    <Stack gap="xs">
                        <Group gap="xs" align="center">
                            <Text fw={600} size="sm">🏆 Jersey Numbers</Text>
                            <Badge color="gold" variant="light" size="xs">
                                {jerseyPlayers.length}
                            </Badge>
                        </Group>
                        
                        <Group gap="xs">
                            {jerseyPlayers.map(player => (
                                <Card
                                    key={player.id}
                                    p="xs"
                                    withBorder
                                    className={`sports-dashboard-card ${selectedPlayerId === player.id ? 'selected' : ''}`}
                                    style={{
                                        cursor: 'pointer',
                                        minWidth: '140px',
                                        border: selectedPlayerId === player.id ? '2px solid var(--sports-primary)' : undefined,
                                        background: selectedPlayerId === player.id ? 'rgba(0, 200, 83, 0.1)' : undefined
                                    }}
                                    onClick={() => onPlayerSelect(player.id === selectedPlayerId ? null : player.id)}
                                >
                                    <Stack gap="xs">
                                        <Group justify="space-between" align="center">
                                            <Badge
                                                className="jersey-badge"
                                                size="lg"
                                            >
                                                #{player.displayValue}
                                            </Badge>
                                            <Text 
                                                size="xs" 
                                                c={getConfidenceColor(player.confidence)}
                                                fw={600}
                                            >
                                                {Math.round(player.confidence * 100)}%
                                            </Text>
                                        </Group>
                                        
                                        {player.currentSpeed !== undefined && (
                                            <Group justify="space-between" align="center">
                                                <Text size="xs" c="dimmed">Speed:</Text>
                                                <Badge 
                                                    color={getSpeedColor(player.currentSpeed)}
                                                    size="xs"
                                                    variant="light"
                                                >
                                                    {player.currentSpeed.toFixed(1)} km/h
                                                </Badge>
                                            </Group>
                                        )}
                                        
                                        {player.timeOnScreen !== undefined && (
                                            <Group justify="space-between" align="center">
                                                <Text size="xs" c="dimmed">On screen:</Text>
                                                <Text size="xs" fw={500}>
                                                    {formatTime(player.timeOnScreen)}
                                                </Text>
                                            </Group>
                                        )}
                                    </Stack>
                                </Card>
                            ))}
                        </Group>
                    </Stack>
                )}

                {/* Track Players Section */}
                {trackPlayers.length > 0 && (
                    <Stack gap="xs">
                        <Group gap="xs" align="center">
                            <Text fw={600} size="sm">🎯 Track IDs</Text>
                            <Badge color="blue" variant="light" size="xs">
                                {trackPlayers.length}
                            </Badge>
                        </Group>
                        
                        <Group gap="xs">
                            {trackPlayers.map(player => (
                                <Card
                                    key={player.id}
                                    p="xs"
                                    withBorder
                                    className={`sports-dashboard-card ${selectedPlayerId === player.id ? 'selected' : ''}`}
                                    style={{
                                        cursor: 'pointer',
                                        minWidth: '120px',
                                        border: selectedPlayerId === player.id ? '2px solid var(--sports-accent)' : undefined,
                                        background: selectedPlayerId === player.id ? 'rgba(33, 150, 243, 0.1)' : undefined
                                    }}
                                    onClick={() => onPlayerSelect(player.id === selectedPlayerId ? null : player.id)}
                                >
                                    <Stack gap="xs">
                                        <Group justify="space-between" align="center">
                                            <Badge
                                                className="track-badge"
                                                size="lg"
                                            >
                                                T{player.displayValue}
                                            </Badge>
                                        </Group>
                                        
                                        {player.currentSpeed !== undefined && (
                                            <Group justify="space-between" align="center">
                                                <Text size="xs" c="dimmed">Speed:</Text>
                                                <Badge 
                                                    color={getSpeedColor(player.currentSpeed)}
                                                    size="xs"
                                                    variant="light"
                                                >
                                                    {player.currentSpeed.toFixed(1)} km/h
                                                </Badge>
                                            </Group>
                                        )}
                                        
                                        {player.timeOnScreen !== undefined && (
                                            <Group justify="space-between" align="center">
                                                <Text size="xs" c="dimmed">On screen:</Text>
                                                <Text size="xs" fw={500}>
                                                    {formatTime(player.timeOnScreen)}
                                                </Text>
                                            </Group>
                                        )}
                                    </Stack>
                                </Card>
                            ))}
                        </Group>
                    </Stack>
                )}

                {/* No players message */}
                {players.length === 0 && (
                    <Card withBorder p="xl" className="sports-dashboard-card">
                        <Stack align="center" gap="md">
                            <Text size="xl">🔍</Text>
                            <Text size="sm" c="dimmed" ta="center">
                                Waiting for player detection...
                                <br />
                                Make sure the pose estimation pipeline is running.
                            </Text>
                        </Stack>
                    </Card>
                )}

                {/* Summary */}
                {players.length > 0 && (
                    <Card withBorder p="sm" style={{ background: 'rgba(0, 200, 83, 0.05)' }}>
                        <Group justify="space-between" align="center">
                            <Text size="sm" fw={600}>Summary:</Text>
                            <Group gap="lg">
                                <Text size="sm">
                                    <Text span fw={600}>{players.length}</Text> total players
                                </Text>
                                <Text size="sm">
                                    <Text span fw={600}>{jerseyPlayers.length}</Text> with jerseys
                                </Text>
                                <Text size="sm">
                                    <Text span fw={600}>
                                        {players.length > 0 ? Math.round((jerseyPlayers.length / players.length) * 100) : 0}%
                                    </Text> detection rate
                                </Text>
                            </Group>
                        </Group>
                    </Card>
                )}
            </Stack>
        </div>
    );
}