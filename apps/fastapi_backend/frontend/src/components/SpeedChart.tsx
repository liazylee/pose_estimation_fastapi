import React, { useCallback, useEffect, useRef, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Button, Group, Stack, Text, Badge, Switch } from '@mantine/core';
import { getDisplayId, getDisplayIdColor, extractDisplayIds, PersonData } from '../utils/displayId';

interface SpeedDataPoint {
    frameIndex: number;
    timestamp: number;
    timeInSeconds: number; // 相对开始时间的秒数
    [key: string]: number; // displayId_speed format: "jersey_10": 15.2 or "track_1": 15.2
}

interface DisplayIdInfo {
    id: string;
    displayValue: number;
    label: string;
    type: 'jersey' | 'track';
    confidence: number;
    fallbackTrackId: number;
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
    selectedDisplayId?: string | null; // Changed from selectedTrackId to selectedDisplayId
    onDisplayIdChange?: (displayId: string | null) => void; // Changed from onTrackIdChange
    showAllTracks?: boolean;
    onShowAllTracksChange?: (showAll: boolean) => void;
    maxDataPoints?: number;
    height?: number;
    jerseyConfidenceThreshold?: number;
}

// Sports-themed color scheme with better contrast
const DISPLAY_COLORS = [
    "#00C853", // Sports green
    "#FF6F00", // Orange
    "#2196F3", // Blue  
    "#E91E63", // Pink
    "#9C27B0", // Purple
    "#FF9800", // Amber
    "#00BCD4", // Cyan
    "#4CAF50", // Green
    "#F44336", // Red
    "#FF5722"  // Deep Orange
];

export default function SpeedChart({
    frameData,
    connectionState,
    connectionError,
    retryInfo,
    onManualReconnect,
    selectedDisplayId = null,
    onDisplayIdChange,
    showAllTracks = false,
    onShowAllTracksChange,
    maxDataPoints = 100,
    height = 300,
    jerseyConfidenceThreshold = 0.7
}: SpeedChartProps) {
    const [speedData, setSpeedData] = useState<SpeedDataPoint[]>([]);
    const [availableDisplayIds, setAvailableDisplayIds] = useState<DisplayIdInfo[]>([]);
    const [startTime, setStartTime] = useState<number | null>(null);
    const [maxTimeRange, setMaxTimeRange] = useState<number>(30); // 初始30秒窗口

    // Reset data when frameData becomes null (manual reconnect)
    useEffect(() => {
        if (frameData === null) {
            setSpeedData([]);
            setStartTime(null);
            setMaxTimeRange(30);
            setAvailableDisplayIds([]);
            return;
        }
    }, [frameData]);

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

        // 提取速度数据 - using display IDs
        const speedPoint: SpeedDataPoint = {
            frameIndex,
            timestamp: currentTimestamp,
            timeInSeconds
        };

        const currentDisplayIds: DisplayIdInfo[] = [];
        
        persons.forEach((person: PersonData) => {
            const displayIdInfo = getDisplayId(person, jerseyConfidenceThreshold);
            let speed = typeof person.speed_kmh === "number" ? person.speed_kmh : 0;
            
            // Only process persons with valid track IDs
            if (displayIdInfo.fallbackTrackId > 0) {
                currentDisplayIds.push(displayIdInfo);
                
                // 获取之前的速度值进行平滑处理
                const prevData = speedData[speedData.length - 1];
                if (prevData && prevData[displayIdInfo.id] !== undefined) {
                    const prevSpeed = prevData[displayIdInfo.id];
                    // 使用简单的移动平均进行平滑，权重70%新值，30%旧值
                    speed = speed * 0.7 + prevSpeed * 0.3;
                }
                
                speedPoint[displayIdInfo.id] = Number(speed.toFixed(2));
            }
        });

        // 更新可用display IDs
        const displayIdStrings = currentDisplayIds.map(d => d.id).sort();
        const currentIdStrings = availableDisplayIds.map(d => d.id).sort();
        if (JSON.stringify(displayIdStrings) !== JSON.stringify(currentIdStrings)) {
            setAvailableDisplayIds(currentDisplayIds);
        }

        setSpeedData(prev => {
            // For better line continuity, ensure all previous display IDs have values in the new point
            // Fill missing display IDs with null or last known value
            const allDisplayIds = new Set([...availableDisplayIds.map(d => d.id), ...currentDisplayIds.map(d => d.id)]);
            allDisplayIds.forEach(displayId => {
                if (speedPoint[displayId] === undefined) {
                    // Try to use the last known value for this display ID to maintain continuity
                    const lastPoint = prev[prev.length - 1];
                    if (lastPoint && lastPoint[displayId] !== undefined) {
                        // Use a slightly decayed value to gradually reduce speed when track is lost
                        speedPoint[displayId] = Math.max(0, lastPoint[displayId] * 0.9);
                    } else {
                        speedPoint[displayId] = 0;
                    }
                }
            });

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
    }, [frameData, availableDisplayIds, maxDataPoints, startTime, maxTimeRange, jerseyConfidenceThreshold]);

    // 清空数据的处理函数
    const handleClearData = useCallback(() => {
        setSpeedData([]);
        setStartTime(null);
        setMaxTimeRange(30); // 重置为30秒窗口
        onManualReconnect();
    }, [onManualReconnect]);

    // 获取要显示的线条 - using display IDs
    const getDisplayLines = () => {
        if (showAllTracks) {
            return availableDisplayIds.map(displayIdInfo => ({
                key: displayIdInfo.id,
                name: displayIdInfo.label,
                color: getDisplayIdColor(displayIdInfo.id, DISPLAY_COLORS),
                type: displayIdInfo.type,
                confidence: displayIdInfo.confidence
            }));
        } else if (selectedDisplayId !== null) {
            const selectedInfo = availableDisplayIds.find(d => d.id === selectedDisplayId);
            if (selectedInfo) {
                return [{
                    key: selectedInfo.id,
                    name: selectedInfo.label,
                    color: getDisplayIdColor(selectedInfo.id, DISPLAY_COLORS),
                    type: selectedInfo.type,
                    confidence: selectedInfo.confidence
                }];
            }
        }
        return [];
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
                    
                    {!showAllTracks && availableDisplayIds.length > 0 && (
                        <select
                            value={selectedDisplayId || ''}
                            onChange={(e) => onDisplayIdChange?.(e.target.value || null)}
                            style={{
                                padding: '4px 8px',
                                borderRadius: '4px',
                                border: '1px solid #ccc'
                            }}
                        >
                            <option value="">Select Player</option>
                            {availableDisplayIds.map(displayIdInfo => (
                                <option key={displayIdInfo.id} value={displayIdInfo.id}>
                                    {displayIdInfo.label}
                                    {displayIdInfo.type === 'jersey' && ` (${Math.round(displayIdInfo.confidence * 100)}%)`}
                                </option>
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
                                type="linear"
                                dataKey={line.key}
                                stroke={line.color}
                                strokeWidth={2}
                                dot={{fill: line.color, strokeWidth: 1, r: 1}}
                                activeDot={{r: 4, fill: line.color}}
                                name={line.name}
                                connectNulls={true}
                                animationDuration={0}
                                isAnimationActive={false}
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
                    Available players: {availableDisplayIds.length > 0 ? 
                        availableDisplayIds.map(d => d.type === 'jersey' ? `#${d.displayValue}` : `T${d.displayValue}`).join(', ') 
                        : 'None'}
                </Text>
                <Text size="sm" c="dimmed">
                    Mode: {showAllTracks ? 'All Players' : selectedDisplayId ? 
                        availableDisplayIds.find(d => d.id === selectedDisplayId)?.label || 'Unknown'
                        : 'None selected'}
                </Text>
            </Group>
        </Stack>
    );
}