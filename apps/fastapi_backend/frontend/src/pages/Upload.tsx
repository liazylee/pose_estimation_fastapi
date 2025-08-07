import { useRef, useState } from 'react';
import { Button, Card, FileInput, Group, Progress, Text } from '@mantine/core';
import { upload } from '@/api';
import { useNavigate } from 'react-router-dom';

export default function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number>(0);
  const [uploading, setUploading] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);
  const navigate = useNavigate();

  const onStart = async () => {
    if (!file) return;
    setUploading(true);
    controllerRef.current = new AbortController();
    try {
      const res = await upload(file, setProgress, controllerRef.current);
      navigate(`/tasks/${res.task_id}`);
    } finally {
      setUploading(false);
    }
  };

  const onCancel = () => {
    controllerRef.current?.abort();
    setUploading(false);
  };

  return (
    <Card withBorder>
      <FileInput label=">500MB 文件可用" placeholder="选择视频文件" value={file} onChange={setFile} accept="video/*" />
      {uploading && (
        <>
          <Progress mt="md" value={progress} />
          <Text size="sm" mt="xs">{progress}%</Text>
        </>
      )}
      <Group mt="md">
        <Button onClick={onStart} disabled={!file || uploading}>开始上传</Button>
        <Button variant="light" color="red" onClick={onCancel} disabled={!uploading}>取消</Button>
      </Group>
    </Card>
  );
}


