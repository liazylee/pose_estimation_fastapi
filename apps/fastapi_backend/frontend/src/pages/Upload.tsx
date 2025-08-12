import {useRef, useState} from 'react';
import {Button, Card, FileInput, Group, Progress, Stack, Text, Title} from '@mantine/core';
import {upload} from '@/api';
import {useNavigate} from 'react-router-dom';

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
        <Stack>
            <Title order={3}>upload a video file</Title>
            <Card withBorder>
                <FileInput label=">500MB max" description="select a video file" placeholder="select a video"
                           value={file} onChange={setFile} accept="video/*"/>
                {uploading && (
                    <>
                        <Progress mt="md" value={progress}/>
                        <Text size="sm" mt="xs">{progress}%</Text>
                    </>
                )}
                <Group mt="md">
                    <Button onClick={onStart} disabled={!file || uploading}>upload</Button>
                    <Button variant="light" color="red" onClick={onCancel} disabled={!uploading}>cancel</Button>
                </Group>
            </Card>
        </Stack>
    );
}


