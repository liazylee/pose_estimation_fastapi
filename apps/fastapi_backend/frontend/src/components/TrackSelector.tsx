// TrackSelector.tsx - Track ID 选择器
import React from 'react';
import {Badge, Button, Group, SegmentedControl, Stack, Text} from '@mantine/core';

type TrackSelectorProps = {
    availableTrackIds: number[];
    selectedTrackId: number | null;
    onTrackIdChange: (trackId: number | null) => void;
    showStats?: boolean;
};

const TRACK_COLORS = ["#00ffff", "#ff00ff", "#ffff00", "#800080", "#ffa500", "#0080ff"];
const getTrackColor = (id: number) => TRACK_COLORS[Math.abs(id) % TRACK_COLORS.length];

export default function TrackSelector({
                                          availableTrackIds,
                                          selectedTrackId,
                                          onTrackIdChange,
                                          showStats = true
                                      }: TrackSelectorProps) {

    // 构建选择器数据
    const selectorData = [
        {label: 'All', value: 'all'},
        ...availableTrackIds.map(id => ({
            label: `Track ${id}`,
            value: id.toString()
        }))
    ];

    const handleChange = (value: string) => {
        if (value === 'all') {
            onTrackIdChange(null);
        } else {
            onTrackIdChange(parseInt(value));
        }
    };

    const currentValue = selectedTrackId === null ? 'all' : selectedTrackId.toString();

    return (
        <Stack gap="sm">
            {/* 统计信息 */}
            {showStats && (
                <Group gap="xs">
                    <Text size="sm" c="dimmed">
                        Available tracks:
                    </Text>
                    {availableTrackIds.length === 0 ? (
                        <Badge color="gray" variant="light">No tracks</Badge>
                    ) : (
                        availableTrackIds.map(id => (
                            <Badge
                                key={id}
                                color={selectedTrackId === id ? "green" : "gray"}
                                variant={selectedTrackId === id ? "filled" : "light"}
                                style={{
                                    borderColor: getTrackColor(id),
                                    borderWidth: selectedTrackId === id ? 2 : 1,
                                    borderStyle: 'solid'
                                }}
                            >
                                {id}
                            </Badge>
                        ))
                    )}
                </Group>
            )}

            {/* 分段控制器 */}
            {availableTrackIds.length > 0 && (
                <SegmentedControl
                    value={currentValue}
                    onChange={handleChange}
                    data={selectorData}
                    size="sm"
                    color="blue"
                />
            )}

            {/* 快速按钮 */}
            {availableTrackIds.length > 1 && (
                <Group gap="xs">
                    <Text size="xs" c="dimmed">Quick select:</Text>
                    <Button
                        size="xs"
                        variant={selectedTrackId === null ? "filled" : "light"}
                        onClick={() => onTrackIdChange(null)}
                        color="gray"
                    >
                        Show All
                    </Button>
                    {availableTrackIds.slice(0, 5).map(id => (
                        <Button
                            key={id}
                            size="xs"
                            variant={selectedTrackId === id ? "filled" : "light"}
                            onClick={() => onTrackIdChange(id)}
                            style={{
                                backgroundColor: selectedTrackId === id ? getTrackColor(id) : undefined,
                                borderColor: getTrackColor(id),
                                color: selectedTrackId === id ? '#000' : getTrackColor(id)
                            }}
                        >
                            {id}
                        </Button>
                    ))}
                    {availableTrackIds.length > 5 && (
                        <Text size="xs" c="dimmed">
                            +{availableTrackIds.length - 5} more
                        </Text>
                    )}
                </Group>
            )}

            {/* 提示信息 */}
            {availableTrackIds.length === 0 && (
                <Text size="sm" c="dimmed" ta="center" p="md">
                    🔍 Waiting for pose detection data...
                </Text>
            )}
        </Stack>
    );
}