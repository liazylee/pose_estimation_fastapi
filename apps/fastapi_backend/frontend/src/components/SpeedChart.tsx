import React, { useCallback, useEffect, useRef, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Button, Group, Stack, Text, Badge, Switch } from '@mantine/core';

interface SpeedDataPoint {
    frameIndex: number;
    timestamp: number;
    timeInSeconds: number; // 相对开始时间的秒数
    [key: string]: number; // trackId_speed format: "track_1": 15.2
}

// WebSocket 连接状态 (从父组件传入)
enum ConnectionState {
    DISCONNECTED = 'disconnected',
    CONNECTING = 'connecting',
    CONNECTED = 'connected',
    RECONNECTING = 'reconnecting',
    ERROR = 'error'
}

interface SpeedChartProps {
    frameData: any; // WebSocket数据从父组件传入
    connectionState: ConnectionState;
    connectionError: string;
    retryInfo: { attempts: number; maxRetries: number };
    onManualReconnect: () => void;
    selectedTrackId?: number | null;
    onTrackIdChange?: (trackId: number | null) => void;
    showAllTracks?: boolean;
    onShowAllTracksChange?: (showAll: boolean) => void;
    maxDataPoints?: number;
    height?: number;
}

const TRACK_COLORS = ["#8884d8", "#82ca9d", "#ffc658", "#ff7300", "#00ff00", "#0088fe", "#ff0080"];

export default function SpeedChart({
    frameData,
    connectionState,
    connectionError,
    retryInfo,
    onManualReconnect,
    selectedTrackId = null,
    onTrackIdChange,
    showAllTracks = false,
    onShowAllTracksChange,
    maxDataPoints = 100,
    height = 300
}: SpeedChartProps) {
    const [speedData, setSpeedData] = useState<SpeedDataPoint[]>([]);
    const [availableTrackIds, setAvailableTrackIds] = useState<number[]>([]);
    const [startTime, setStartTime] = useState<number | null>(null);
    const [maxTimeRange, setMaxTimeRange] = useState<number>(30); // 初始30秒窗口

    // 处理传入的帧数据
    useEffect(() => {
        if (!frameData) return;

        const frame = frameData?.tracked_poses_results ? frameData : frameData?.results?.[0];
        if (!frame) return;

        const frameIndex = frame.frame_id || Date.now();
        const currentTimestamp = performance.now();
        const persons = frame.tracked_poses_results || [];

        // 初始化开始时间
        if (startTime === null) {
            setStartTime(currentTimestamp);
        }

        // 计算相对时间（秒）
        const timeInSeconds = startTime !== null ? (currentTimestamp - startTime) / 1000 : 0;

        // 提取速度数据
        const speedPoint: SpeedDataPoint = {
            frameIndex,
            timestamp: currentTimestamp,
            timeInSeconds
        };

        const currentTrackIds: number[] = [];
        
        persons.forEach((person: any) => {
            const trackId = person.track_id ?? 0;
            let speed = typeof person.speed_kmh === "number" ? person.speed_kmh : 0;
            
            if (trackId > 0) {
                currentTrackIds.push(trackId);
                
                // 获取之前的速度值进行平滑处理
                const prevData = speedData[speedData.length - 1];
                if (prevData && prevData[`track_${trackId}`] !== undefined) {
                    const prevSpeed = prevData[`track_${trackId}`];
                    // 使用简单的移动平均进行平滑，权重70%新值，30%旧值
                    speed = speed * 0.7 + prevSpeed * 0.3;
                }
                
                speedPoint[`track_${trackId}`] = Number(speed.toFixed(2));
            }
        });

        // 更新可用track IDs
        if (JSON.stringify(currentTrackIds) !== JSON.stringify(availableTrackIds)) {
            setAvailableTrackIds(currentTrackIds);
        }

        setSpeedData(prev => {
            const newData = [...prev, speedPoint];
            
            // 动态调整时间窗口
            if (timeInSeconds > maxTimeRange) {
                // 当超过当前窗口时，扩展窗口
                const newRange = Math.max(maxTimeRange * 1.5, timeInSeconds + 10);
                setMaxTimeRange(newRange);
            }
            
            // 只保留当前时间窗口内的数据，避免图表过度拥挤
            const timeThreshold = Math.max(0, timeInSeconds - maxTimeRange);
            const filteredData = newData.filter(point => point.timeInSeconds >= timeThreshold);
            
            // 额外限制数据点数量
            if (filteredData.length > maxDataPoints) {
                return filteredData.slice(-maxDataPoints);
            }
            
            return filteredData;
        });
    }, [frameData, availableTrackIds, maxDataPoints, startTime, maxTimeRange]);

    // 清空数据的处理函数
    const handleClearData = useCallback(() => {
        setSpeedData([]);
        setStartTime(null);
        setMaxTimeRange(30); // 重置为30秒窗口
        onManualReconnect();
    }, [onManualReconnect]);

    // 获取要显示的线条
    const getDisplayLines = () => {
        if (showAllTracks) {
            return availableTrackIds.map(trackId => ({
                key: `track_${trackId}`,
                name: `Track ${trackId}`,
                color: TRACK_COLORS[trackId % TRACK_COLORS.length]
            }));
        } else if (selectedTrackId !== null) {
            return [{
                key: `track_${selectedTrackId}`,
                name: `Track ${selectedTrackId}`,
                color: TRACK_COLORS[selectedTrackId % TRACK_COLORS.length]
            }];
        } else {
            return [];
        }
    };

    const displayLines = getDisplayLines();

    // 计算合适的X轴刻度间隔
    const getXAxisTicks = () => {
        if (speedData.length === 0) return [];
        
        const minTime = Math.min(...speedData.map(d => d.timeInSeconds));
        const maxTime = Math.max(...speedData.map(d => d.timeInSeconds));
        const timeRange = maxTime - minTime;
        
        // 根据时间范围动态调整刻度间隔
        let tickInterval: number;
        if (timeRange <= 30) {
            tickInterval = 5; // 5秒间隔
        } else if (timeRange <= 60) {
            tickInterval = 10; // 10秒间隔
        } else if (timeRange <= 300) {
            tickInterval = 30; // 30秒间隔
        } else {
            tickInterval = 60; // 1分钟间隔
        }
        
        const ticks: number[] = [];
        const startTick = Math.floor(minTime / tickInterval) * tickInterval;
        
        for (let tick = startTick; tick <= maxTime + tickInterval; tick += tickInterval) {
            if (tick >= minTime) {
                ticks.push(tick);
            }
        }
        
        return ticks;
    };

    // 格式化时间显示
    const formatTime = (timeInSeconds: number) => {
        const minutes = Math.floor(timeInSeconds / 60);
        const seconds = Math.floor(timeInSeconds % 60);
        if (minutes > 0) {
            return `${minutes}:${seconds.toString().padStart(2, '0')}`;
        } else {
            return `${seconds}s`;
        }
    };

    // 获取X轴的域值
    const getXDomain = () => {
        if (speedData.length === 0) return [0, 30];
        
        const minTime = Math.min(...speedData.map(d => d.timeInSeconds));
        const maxTime = Math.max(...speedData.map(d => d.timeInSeconds));
        
        // 给最大值增加一点缓冲
        const buffer = Math.max(2, (maxTime - minTime) * 0.05);
        return [Math.max(0, minTime - buffer), maxTime + buffer];
    };

    // 获取连接状态信息
    const getConnectionStatusInfo = () => {
        switch (connectionState) {
            case ConnectionState.CONNECTED:
                return { icon: "🟢", text: "Connected", color: "#44ff44" };
            case ConnectionState.CONNECTING:
                return { icon: "🟡", text: "Connecting...", color: "#ffaa00" };
            case ConnectionState.RECONNECTING:
                return { icon: "🟡", text: `Reconnecting... (${retryInfo.attempts}/${retryInfo.maxRetries})`, color: "#ffaa00" };
            case ConnectionState.ERROR:
                return { icon: "🔴", text: connectionError || "Connection Error", color: "#ff4444" };
            case ConnectionState.DISCONNECTED:
            default:
                return { icon: "⚫", text: "Disconnected", color: "#666666" };
        }
    };

    const connectionStatus = getConnectionStatusInfo();

    return (
        <Stack gap="md">
            {/* 控制面板 */}
            <Group justify="space-between" align="center">
                <Group>
                    <Text fw={600}>Speed Tracking</Text>
                    <Badge 
                        color={connectionState === ConnectionState.CONNECTED ? 'green' : 'red'}
                        leftSection={connectionStatus.icon}
                    >
                        {connectionStatus.text}
                    </Badge>
                </Group>

                <Group>
                    <Switch
                        label="Show All Tracks"
                        checked={showAllTracks}
                        onChange={(e) => onShowAllTracksChange?.(e.currentTarget.checked)}
                    />
                    
                    {!showAllTracks && availableTrackIds.length > 0 && (
                        <select
                            value={selectedTrackId || ''}
                            onChange={(e) => onTrackIdChange?.(e.target.value ? Number(e.target.value) : null)}
                            style={{
                                padding: '4px 8px',
                                borderRadius: '4px',
                                border: '1px solid #ccc'
                            }}
                        >
                            <option value="">Select Track</option>
                            {availableTrackIds.map(id => (
                                <option key={id} value={id}>Track {id}</option>
                            ))}
                        </select>
                    )}

                    <Button
                        size="xs"
                        variant="outline"
                        onClick={handleClearData}
                        leftSection="🔄"
                    >
                        Retry
                    </Button>
                </Group>
            </Group>

            {/* 图表区域 */}
            <div style={{ width: '100%', height }}>
                <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={speedData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis 
                            dataKey="timeInSeconds" 
                            type="number"
                            scale="linear"
                            domain={getXDomain()}
                            ticks={getXAxisTicks()}
                            tickFormatter={formatTime}
                            interval={0}
                            minTickGap={50}
                        />
                        <YAxis 
                            label={{ value: 'Speed (km/h)', angle: -90, position: 'insideLeft' }}
                            domain={[0, 'dataMax + 5']}
                        />
                        <Tooltip 
                            labelFormatter={(value) => `Time: ${formatTime(Number(value))}`}
                            formatter={(value: number, name: string) => [
                                `${value.toFixed(1)} km/h`, 
                                name
                            ]}
                        />
                        <Legend />
                        
                        {displayLines.map(line => (
                            <Line
                                key={line.key}
                                type="monotone"
                                dataKey={line.key}
                                stroke={line.color}
                                strokeWidth={2}
                                dot={false}
                                name={line.name}
                                connectNulls={false}
                                strokeDasharray={undefined}
                                animationDuration={300}
                            />
                        ))}
                    </LineChart>
                </ResponsiveContainer>
            </div>

            {/* 统计信息 */}
            <Group gap="md" justify="space-between">
                <Text size="sm" c="dimmed">
                    Data points: {speedData.length}/{maxDataPoints}
                </Text>
                <Text size="sm" c="dimmed">
                    Time window: {maxTimeRange.toFixed(0)}s
                </Text>
                <Text size="sm" c="dimmed">
                    Available tracks: {availableTrackIds.length > 0 ? availableTrackIds.join(', ') : 'None'}
                </Text>
                <Text size="sm" c="dimmed">
                    Mode: {showAllTracks ? 'All Tracks' : selectedTrackId ? `Track ${selectedTrackId}` : 'None selected'}
                </Text>
            </Group>
        </Stack>
    );
}