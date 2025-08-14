import {useEffect, useMemo, useRef, useState} from 'react';
import Hls from 'hls.js';
import {Alert, Badge, Stack, Text} from '@mantine/core';

type Props = {
    path: string; // e.g. "outstream_<task_id>"
    onSizeReady?: (width: number, height: number) => void;
};

// 放在组件外或上方
async function waitForManifest(url: string, timeoutMs = 30000, intervalMs = 1000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
        try {
            const res = await fetch(url, {method: 'GET', cache: 'no-store'});
            if (res.ok) {
                // Additional check: try GET request to ensure content is available
                const getRes = await fetch(url, {method: 'GET', cache: 'no-store'});
                if (getRes.ok && getRes.headers.get('content-length') !== '0') {
                    return true;
                }
            }
        } catch {
        }
        await new Promise(r => setTimeout(r, intervalMs));
    }
    return false;
}

export default function MediaPlayerHLS({path, onSizeReady}: Props) {
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const [error, setError] = useState<string | null>(null);

    // HLS 入口： http://<host>:8889/<path>/index.m3u8
    const hlsUrl = useMemo(() => `http://localhost:8889/${path}/index.m3u8`, [path]);

    useEffect(() => {
        const video = videoRef.current;
        if (!video) return;

        const handleLoaded = () => {
            if (video.videoWidth && video.videoHeight && typeof onSizeReady === 'function') {
                onSizeReady(video.videoWidth, video.videoHeight);
            }
        };

        video.addEventListener('loadedmetadata', handleLoaded);
        return () => {
            video.removeEventListener('loadedmetadata', handleLoaded);
        };
    }, [onSizeReady]);

    // HLS 播放逻辑
    useEffect(() => {
        let hls: Hls | null = null;
        let destroyed = false;

        (async () => {
            setError(null);
            const video = videoRef.current;
            if (!video) return;

            const ready = await waitForManifest(hlsUrl);
            if (!ready) {
                setError('HLS manifest not ready (timeout)');
                return;
            }
            if (destroyed) return;

            try {
                if (Hls.isSupported()) {
                    hls = new Hls({
                        lowLatencyMode: true,
                        manifestLoadingRetryDelay: 1000,
                        levelLoadingRetryDelay: 1000,
                        fragLoadingRetryDelay: 1000,
                    });
                    hls.loadSource(hlsUrl);
                    hls.attachMedia(video);
                    hls.on(Hls.Events.MANIFEST_PARSED, () => {
                        video.play().catch(() => {
                        });
                    });
                    hls.on(Hls.Events.ERROR, (_e, data) => {
                        if (data.fatal) setError('HLS Playback failed: ' + data.type);
                    });
                } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                    video.src = hlsUrl;
                    video.play().catch(() => {
                    });
                } else {
                    setError('HLS is not supported in this browser');
                }
            } catch (e: any) {
                setError(e?.message || 'HLS Playback failed');
            }
        })();

        return () => {
            destroyed = true;
            try {
                if (hls) hls.destroy();
                const v = videoRef.current;
                if (v) {
                    v.pause();
                    v.removeAttribute('src');
                    v.load();
                }
            } catch {
            }
        };
    }, [hlsUrl]);
    return (
        <Stack>
            {error && <Alert color="red">{error}</Alert>}
            <video
                ref={videoRef}
                playsInline
                controls
                style={{width: '100%', background: '#000', minHeight: 300}}
            />
            <Text size="xs" c="dimmed">
                Path: <Badge variant="light">{path}</Badge>
            </Text>
        </Stack>
    );
}
