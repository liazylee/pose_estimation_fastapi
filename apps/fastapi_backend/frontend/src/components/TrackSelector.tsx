// TrackSelector.tsx - Player Display ID 选择器
import React from 'react';
import {Alert, SegmentedControl, Stack, Text} from '@mantine/core';
import '@/styles/sports-theme.css';

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
};

export default function TrackSelector({
                                          availableDisplayIds,
                                          selectedDisplayId,
                                          onDisplayIdChange
                                      }: TrackSelectorProps) {

    // 构建选择器数据 - using display IDs
    const selectorData = availableDisplayIds.map(displayIdInfo => ({
        label: displayIdInfo.label + (displayIdInfo.type === 'jersey' ? ` (${Math.round(displayIdInfo.confidence * 100)}%)` : ''),
        value: displayIdInfo.id
    }))

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
            {availableDisplayIds.length > 0 && (
                <div className="segmented-scroll-x">
                    <SegmentedControl
                        value={currentValue}
                        onChange={handleChange}
                        data={selectorData}
                        size="sm"
                        color="blue"
                    />
                </div>
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
