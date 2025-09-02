import React, { useRef,useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Group, Stack, Text } from '@mantine/core';
import { getDisplayId, getDisplayIdColor, PersonData } from '@/utils/displayId';
import { useGlobalStore } from '@/store/global';

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

interface SpeedChartProps {
    frameData: any; // WebSocket数据从父组件传入
    selectedDisplayId?: string | null; // Changed from selectedTrackId to selectedDisplayId
    showAllTracks?: boolean;
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
    selectedDisplayId = null,
    showAllTracks = false,
    height = 400,
    jerseyConfidenceThreshold = 0.7
}: SpeedChartProps) {
    // 视频总时长（秒）
    const videoDuration = useGlobalStore(s => s.videoDuration);
    // 流视频是否已暂停
    const isVideoPaused = useGlobalStore(s => s.isVideoPaused);

    const [speedData, setSpeedData] = useState<SpeedDataPoint[]>([]);
    const [availableDisplayIds, setAvailableDisplayIds] = useState<DisplayIdInfo[]>([]);
    const [startTime, setStartTime] = useState<number | null>(null);

    const lastFrameTimeRef = useRef<number | null>(null);
    const desiredFPS = 3;
    const frameInterval = 1000 / desiredFPS;

    // Reset data when frameData becomes null (manual reconnect)
    useEffect(() => {
        if (frameData === null) {
            setSpeedData([]);
            setStartTime(null);
            setAvailableDisplayIds([]);
            return;
        }
    }, [frameData]);

    // 处理传入的帧数据
    useEffect(() => {
        if (!frameData) return;

        // 流视频暂停时不更新数据
        if (isVideoPaused) return;

        const frame = frameData?.tracked_poses_results ? frameData : frameData?.results?.[0];
        if (!frame) return;

        const currentTimestamp = performance.now();
        if (lastFrameTimeRef.current !== null &&
            currentTimestamp - lastFrameTimeRef.current < frameInterval) {
            return;
        }
        lastFrameTimeRef.current = currentTimestamp;

        const frameIndex = frame.frame_id || Date.now();
        const persons = frame.tracked_poses_results || [];

        // 初始化开始时间
        if (startTime === null) setStartTime(currentTimestamp);

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
            const info = getDisplayId(person, jerseyConfidenceThreshold);
            let speed = typeof person.speed_kmh === 'number' ? person.speed_kmh : 0;

            if (info.fallbackTrackId > 0) {
                currentDisplayIds.push(info);

                const prev = speedData[speedData.length - 1];
                if (prev && prev[info.id] !== undefined) {
                    const prevSpeed = prev[info.id];
                    speed = speed * 0.7 + prevSpeed * 0.3;
                }

                speedPoint[info.id] = Number(speed.toFixed(2));
            }
        });

        const currentIds = currentDisplayIds.map(d => d.id).sort();
        const savedIds = availableDisplayIds.map(d => d.id).sort();
        if (JSON.stringify(currentIds) !== JSON.stringify(savedIds)) {
            setAvailableDisplayIds(currentDisplayIds);
        }

        const allIds = new Set([...availableDisplayIds.map(d => d.id), ...currentDisplayIds.map(d => d.id)]);
        allIds.forEach(id => {
            if (speedPoint[id] === undefined) {
                const last = speedData[speedData.length - 1];
                speedPoint[id] = last && last[id] !== undefined ? Math.max(0, last[id] * 0.9) : 0;
            }
        });

        setSpeedData(prev => [...prev, speedPoint]);
    }, [frameData, availableDisplayIds, startTime]);

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
        if (typeof videoDuration !== 'number' || isNaN(videoDuration)) return [];
        const interval = videoDuration <= 60 ? 1 : 5;
        return Array.from({ length: Math.floor(videoDuration / interval) + 1 }, (_, i) => i * interval);
    };

    // 格式化时间显示
    const formatTime = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

    // 获取X轴的域值
    const getXDomain = () => {
        if (typeof videoDuration === 'number' && !isNaN(videoDuration)) return [0, videoDuration];
        if (speedData.length === 0) return [0, 30];
        const min = Math.min(...speedData.map(d => d.timeInSeconds));
        const max = Math.max(...speedData.map(d => d.timeInSeconds));
        const buffer = Math.max(2, (max - min) * 0.05);
        return [Math.max(0, min - buffer), max + buffer];
    };

    const chartWidth = videoDuration && videoDuration > 300 ? `${videoDuration * 20}px` : '100%';

    return (
        <Stack gap="md">
            {/* 图表区域 */}
            <div style={{ width: '100%', overflowX: 'auto' }}>
                <div style={{ minWidth: chartWidth, height }}>
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
                                formatter={(value: number, name: string) => [`${value.toFixed(1)} km/h`, name]}
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
            </div>

            {isVideoPaused && (
                <Text size="sm" c="dimmed" ta="center">
                    ▶ Video paused – speed chart updates stopped
                </Text>
            )}

            {/* 统计信息 */}
            <Group gap="md" justify="space-between">
                <Text size="sm" c="dimmed">Data points: {speedData.length}</Text>
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
