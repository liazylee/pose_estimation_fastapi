import { useEffect, useMemo, useRef, useState } from 'react';
import Hls from 'hls.js';
import { Alert, Badge, Button, Group, Stack, Text } from '@mantine/core';
import { useGlobalStore } from '@/store/global';
import { streamApi } from '@/api/http';

type Props = {
    path: string; // e.g. "outstream_<task_id>"
    onSizeReady?: (width: number, height: number) => void;
};

type StreamType = 'hls' | 'webrtc';

const hlsHost = import.meta.env.VITE_API_HLS;
const webrtcHost = import.meta.env.VITE_API_WEBRTC;

export default function MediaPlayer({ path, onSizeReady }: Props) {
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [streamType, setStreamType] = useState<StreamType>('hls');
    const [isConnecting, setIsConnecting] = useState(false);

    const isM3u8Ready = useGlobalStore(s => s.isM3u8Ready);

    const hlsUrl = useMemo(() => `${hlsHost}/${path}/index.m3u8`, [path, hlsHost]);
    const webrtcApiUrl = useMemo(() => `${webrtcHost}/${path}/whep`, [path, webrtcHost]);

    // 自动探测 m3u8 状态
    useEffect(() => {
        const checkM3u8 = async () => {
            try {
                await streamApi.get(`/${path}/index.m3u8`);
            } catch {}
        };
        if(path){
            checkM3u8()
        }
    }, [path]);

    // 通知外部尺寸准备完毕
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

    const setupWebRTC = async () => {
        setIsConnecting(true);
        setError(null);
        const video = videoRef.current;
        if (!video) {
            setIsConnecting(false);
            return null;
        }

        try {
            const peerConnection = new RTCPeerConnection({
                iceServers: [
                    { urls: 'stun:stun.l.google.com:19302' },
                    { urls: 'stun:stun1.l.google.com:19302' }
                ]
            });

            peerConnection.oniceconnectionstatechange = () => {
                if (['connected', 'completed'].includes(peerConnection.iceConnectionState)) {
                    setIsConnecting(false);
                } else if (['failed', 'disconnected'].includes(peerConnection.iceConnectionState)) {
                    setError('WebRTC connection failed');
                    setIsConnecting(false);
                }
            };

            peerConnection.ontrack = (event) => {
                if (event.streams && event.streams[0]) {
                    video.srcObject = event.streams[0];
                    video.play().catch(console.error);
                }
            };

            peerConnection.addTransceiver('video', { direction: 'recvonly' });
            const offer = await peerConnection.createOffer();
            await peerConnection.setLocalDescription(offer);

            const response = await fetch(webrtcApiUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/sdp' },
                body: offer.sdp
            });

            if (!response.ok) throw new Error(`WHEP request failed: ${response.status}`);
            const answerSdp = await response.text();
            await peerConnection.setRemoteDescription({ type: 'answer', sdp: answerSdp });

            return { peerConnection };
        } catch (e: any) {
            setError(`WebRTC setup failed: ${e.message}`);
            setIsConnecting(false);
            return null;
        }
    };

    const setupHLS = async () => {
        setIsConnecting(true);
        setError(null);
        const video = videoRef.current;
        if (!video) {
            setIsConnecting(false);
            return null;
        }

        try {
            if (Hls.isSupported()) {
                const hls = new Hls({
                    lowLatencyMode: true,
                    manifestLoadingRetryDelay: 1000,
                    levelLoadingRetryDelay: 1000,
                    fragLoadingRetryDelay: 1000,
                });
                hls.loadSource(hlsUrl);
                hls.attachMedia(video);
                hls.on(Hls.Events.MANIFEST_PARSED, () => {
                    video.play().catch(() => {});
                    setIsConnecting(false);
                });
                hls.on(Hls.Events.ERROR, (_e, data) => {
                    if (data.fatal) {
                        setError('HLS Playback failed: ' + data.type);
                        setIsConnecting(false);
                    }
                });
                return { hls };
            } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                video.src = hlsUrl;
                video.play().catch(() => {});
                setIsConnecting(false);
                return { hls: null };
            } else {
                setError('HLS is not supported in this browser');
                setIsConnecting(false);
                return null;
            }
        } catch (e: any) {
            setError(e?.message || 'HLS playback failed');
            setIsConnecting(false);
            return null;
        }
    };

    // ⚠️ 仅当 isM3u8Ready 为 true 时才 setupHLS
    useEffect(() => {
        if (streamType !== 'hls') return;
        if (!isM3u8Ready) return;

        let cleanup: (() => void) | null = null;

        const setup = async () => {
            const result = await setupHLS();
            if (result?.hls) {
                cleanup = () => {
                    try {
                        result.hls!.destroy();
                    } catch {}
                };
            }
        };
        setup();

        return () => {
            if (cleanup) cleanup();
        };
    }, [isM3u8Ready, streamType, path]);

    // WebRTC 逻辑不变
    useEffect(() => {
        if (streamType !== 'webrtc') return;

        let cleanup: (() => void) | null = null;

        const setup = async () => {
            const result = await setupWebRTC();
            if (result?.peerConnection) {
                cleanup = () => {
                    try {
                        result.peerConnection.close();
                    } catch {}
                };
            }
        };
        setup();

        return () => {
            if (cleanup) cleanup();
            const v = videoRef.current;
            if (v) {
                try {
                    v.pause();
                    v.srcObject = null;
                    v.removeAttribute('src');
                    v.load();
                } catch {}
            }
        };
    }, [streamType, webrtcApiUrl]);

    return (
        <Stack>
            <Group>
                <Button
                    variant={streamType === 'hls' ? 'filled' : 'outline'}
                    onClick={() => setStreamType('hls')}
                    loading={streamType === 'hls' && isConnecting}
                    disabled={!isM3u8Ready}
                >
                    HLS
                </Button>
                <Button
                    variant={streamType === 'webrtc' ? 'filled' : 'outline'}
                    onClick={() => setStreamType('webrtc')}
                    loading={streamType === 'webrtc' && isConnecting}
                >
                    WebRTC
                </Button>
            </Group>

            {error && <Alert color="red">{error}</Alert>}

            <video
                ref={videoRef}
                playsInline
                controls
                style={{ width: '100%', background: '#000', minHeight: 300 }}
            />

            <Group>
                <Text size="xs" c="dimmed">
                    Path: <Badge variant="light">{path}</Badge>
                </Text>
                <Text size="xs" c="dimmed">
                    Mode: <Badge variant="light" color={streamType === 'webrtc' ? 'blue' : 'green'}>{streamType.toUpperCase()}</Badge>
                </Text>
                {streamType === 'webrtc' && (
                    <Text size="xs" c="dimmed">
                        WebRTC: <Badge variant="light" color="orange">{webrtcHost}</Badge>
                    </Text>
                )}
            </Group>
        </Stack>
    );
}
