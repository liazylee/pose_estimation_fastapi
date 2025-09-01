import React, { useCallback, useEffect, useRef, useState } from 'react';
import { 
  Stack, 
  Table, 
  Button, 
  Badge, 
  Text, 
  Group, 
  Pagination, 
  Card, 
  Loader, 
  Center,
  ActionIcon,
  Title,
  Container,
  SimpleGrid
} from '@mantine/core';
import { Play, Clock, File } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { getVideoRecords } from '../api';
import type { VideoRecord } from '../api/types';
import { notifications } from '@mantine/notifications';


export default function VideoHistory() {
  const [records, setRecords] = useState<VideoRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize] = useState(10);
  const navigate = useNavigate();

  const loadRecords = useCallback(async () => {
    try {
      setLoading(true);
      const response = await getVideoRecords(pageSize, (currentPage - 1) * pageSize);
      setRecords(response.records);
      setTotal(response.count);
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: 'Failed to load video records',
        color: 'red'
      });
    } finally {
      setLoading(false);
    }
  }, [currentPage, pageSize]);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return 'Unknown';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
  };

  const formatDuration = (seconds?: number) => {
    if (!seconds) return 'Unknown';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString();
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'completed': return 'green';
      case 'processing': return 'blue';
      case 'failed': return 'red';
      case 'pending': return 'yellow';
      case 'initializing': return 'orange';
      default: return 'gray';
    }
  };

  const handlePlayVideo = (record: VideoRecord) => {
    if (record.status.toLowerCase() !== 'completed') {
      notifications.show({
        title: 'Error',
        message: 'Video is not completed yet',
        color: 'red'
      });
      return;
    }
    
    navigate(`/video-analysis/${record.task_id}`, { 
      state: { record } 
    });
  };

  return (
    <Container size="xl" px="md">
      <Group justify="space-between" align="center" mb="xl">
        <Title order={2}>Video History</Title>
        <Button onClick={loadRecords} leftSection={<Clock size={16} />}>
          Refresh
        </Button>
      </Group>

      {loading ? (
        <Center h={200}>
          <Loader />
        </Center>
      ) : (
        <>
          <Card>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Filename</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Created At</Table.Th>
                  <Table.Th>File Size</Table.Th>
                  <Table.Th>Duration</Table.Th>
                  <Table.Th>Actions</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {records.map((record) => (
                  <Table.Tr key={record.task_id}>
                    <Table.Td>
                      <Group gap="xs">
                        <File size={16} />
                        <Text size="sm" truncate style={{ maxWidth: 200 }}>
                          {record.filename}
                        </Text>
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Badge color={getStatusColor(record.status)} size="sm">
                        {record.status}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c="dimmed">
                        {formatDate(record.created_at)}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{formatFileSize(record.file_size)}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{formatDuration(record.duration)}</Text>
                    </Table.Td>
                    <Table.Td>
                      <ActionIcon
                        variant="light"
                        color="blue"
                        onClick={() => handlePlayVideo(record)}
                        disabled={record.status.toLowerCase() !== 'completed'}
                      >
                        <Play size={16} />
                      </ActionIcon>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Card>

          {Math.ceil(total / pageSize) > 1 && (
            <Group justify="center">
              <Pagination
                total={Math.ceil(total / pageSize)}
                value={currentPage}
                onChange={setCurrentPage}
              />
            </Group>
          )}
        </>
      )}

    </Container>
  );
}