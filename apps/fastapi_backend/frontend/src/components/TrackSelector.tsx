// TrackSelector.tsx - Player Display ID 选择器
import React from 'react';
import {Badge, Button, Group, SegmentedControl, Stack, Text} from '@mantine/core';
import { getDisplayIdColor } from '../utils/displayId';

interface DisplayIdInfo {
    id: string;
    displayValue: number;
    label: string;
    type: 'jersey' | 'track';
    confidence: number;
    fallbackTrackId: number;
}

type TrackSelectorProps = {
    availableDisplayIds: DisplayIdInfo[];
    selectedDisplayId: string | null;
    onDisplayIdChange: (displayId: string | null) => void;
    showStats?: boolean;
};

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

export default function TrackSelector({
                                          availableDisplayIds,
                                          selectedDisplayId,
                                          onDisplayIdChange,
                                          showStats = true
                                      }: TrackSelectorProps) {

    // 构建选择器数据 - using display IDs
    const selectorData = [
        {label: 'All Players', value: 'all'},
        ...availableDisplayIds.map(displayIdInfo => ({
            label: displayIdInfo.label + (displayIdInfo.type === 'jersey' ? ` (${Math.round(displayIdInfo.confidence * 100)}%)` : ''),
            value: displayIdInfo.id
        }))
    ];

    const handleChange = (value: string) => {
        if (value === 'all') {
            onDisplayIdChange(null);
        } else {
            onDisplayIdChange(value);
        }
    };

    const currentValue = selectedDisplayId === null ? 'all' : selectedDisplayId;

    return (
        <Stack gap="sm">
            {/* 统计信息 */}
            {showStats && (
                <Group gap="xs">
                    <Text size="sm" c="dimmed">
                        Available players:
                    </Text>
                    {availableDisplayIds.length === 0 ? (
                        <Badge color="gray" variant="light">No players</Badge>
                    ) : (
                        availableDisplayIds.map(displayIdInfo => (
                            <Badge
                                key={displayIdInfo.id}
                                color={selectedDisplayId === displayIdInfo.id ? "green" : "gray"}
                                variant={selectedDisplayId === displayIdInfo.id ? "filled" : "light"}
                                style={{
                                    borderColor: getDisplayIdColor(displayIdInfo.id, DISPLAY_COLORS),
                                    borderWidth: selectedDisplayId === displayIdInfo.id ? 2 : 1,
                                    borderStyle: 'solid',
                                    fontWeight: displayIdInfo.type === 'jersey' ? 'bold' : 'normal'
                                }}
                            >
                                {displayIdInfo.type === 'jersey' ? `#${displayIdInfo.displayValue}` : `T${displayIdInfo.displayValue}`}
                                {displayIdInfo.type === 'jersey' && (
                                    <Text span size="xs" c="dimmed" ml={4}>
                                        {Math.round(displayIdInfo.confidence * 100)}%
                                    </Text>
                                )}
                            </Badge>
                        ))
                    )}
                </Group>
            )}

            {/* 分段控制器 */}
            {availableDisplayIds.length > 0 && (
                <SegmentedControl
                    value={currentValue}
                    onChange={handleChange}
                    data={selectorData}
                    size="sm"
                    color="blue"
                />
            )}

            {/* 快速按钮 */}
            {availableDisplayIds.length > 1 && (
                <Group gap="xs">
                    <Text size="xs" c="dimmed">Quick select:</Text>
                    <Button
                        size="xs"
                        variant={selectedDisplayId === null ? "filled" : "light"}
                        onClick={() => onDisplayIdChange(null)}
                        color="gray"
                    >
                        Show All
                    </Button>
                    {availableDisplayIds.slice(0, 5).map(displayIdInfo => {
                        const color = getDisplayIdColor(displayIdInfo.id, DISPLAY_COLORS);
                        return (
                            <Button
                                key={displayIdInfo.id}
                                size="xs"
                                variant={selectedDisplayId === displayIdInfo.id ? "filled" : "light"}
                                onClick={() => onDisplayIdChange(displayIdInfo.id)}
                                style={{
                                    backgroundColor: selectedDisplayId === displayIdInfo.id ? color : undefined,
                                    borderColor: color,
                                    color: selectedDisplayId === displayIdInfo.id ? '#000' : color,
                                    fontWeight: displayIdInfo.type === 'jersey' ? 'bold' : 'normal'
                                }}
                            >
                                {displayIdInfo.type === 'jersey' ? `#${displayIdInfo.displayValue}` : `T${displayIdInfo.displayValue}`}
                            </Button>
                        );
                    })}
                    {availableDisplayIds.length > 5 && (
                        <Text size="xs" c="dimmed">
                            +{availableDisplayIds.length - 5} more
                        </Text>
                    )}
                </Group>
            )}

            {/* 提示信息 */}
            {availableDisplayIds.length === 0 && (
                <Text size="sm" c="dimmed" ta="center" p="md">
                    🔍 Waiting for pose detection data...
                </Text>
            )}
        </Stack>
    );
}