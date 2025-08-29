import {useEffect, useMemo, useRef, useState} from 'react';
import Hls from 'hls.js';
import {Alert, Badge, Button, Group, Stack, Text} from '@mantine/core';

type Props = {
    path: string; // e.g. "outstream_<task_id>"
    onSizeReady?: (width: number, height: number) => void;
};

type StreamType = 'hls' | 'webrtc';

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

export default function MediaPlayer({path, onSizeReady}: Props) {
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [streamType, setStreamType] = useState<StreamType>('hls');
    const [isConnecting, setIsConnecting] = useState(false);
    
    // HLS 入口： http://<host>:8889/<path>/index.m3u8
    const hlsUrl = useMemo(() => `http://localhost:8889/${path}/index.m3u8`, [path]);
    
    // WebRTC 入口： MediaMTX HTTP API
    const webrtcApiUrl = useMemo(() => `http://localhost:8888/${path}/whep`, [path]);

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

    // WebRTC 播放逻辑 (MediaMTX WHEP)
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
                    {urls: 'stun:stun.l.google.com:19302'},
                    {urls: 'stun:stun1.l.google.com:19302'}
                ]
            });

            peerConnection.oniceconnectionstatechange = () => {
                console.log('ICE Connection State:', peerConnection.iceConnectionState);
                if (peerConnection.iceConnectionState === 'connected' || 
                    peerConnection.iceConnectionState === 'completed') {
                    setIsConnecting(false);
                }
                if (peerConnection.iceConnectionState === 'failed' || 
                    peerConnection.iceConnectionState === 'disconnected') {
                    setError('WebRTC connection failed');
                    setIsConnecting(false);
                }
            };

            peerConnection.ontrack = (event) => {
                console.log('Received track:', event);
                if (event.streams && event.streams[0]) {
                    video.srcObject = event.streams[0];
                    video.play().catch((e) => {
                        console.error('Video play failed:', e);
                    });
                }
            };

            // 添加接收器用于视频
            peerConnection.addTransceiver('video', {direction: 'recvonly'});

            // 创建 offer
            const offer = await peerConnection.createOffer();
            await peerConnection.setLocalDescription(offer);

            // 使用 WHEP 协议发送 offer 到 MediaMTX
            const response = await fetch(webrtcApiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/sdp',
                },
                body: offer.sdp
            });

            if (!response.ok) {
                throw new Error(`WHEP request failed: ${response.status} ${response.statusText}`);
            }

            // 获取 answer SDP
            const answerSdp = await response.text();
            await peerConnection.setRemoteDescription({
                type: 'answer',
                sdp: answerSdp
            });

            console.log('WebRTC connection established via WHEP');
            
            return {peerConnection};
        } catch (e: any) {
            console.error('WebRTC setup error:', e);
            setError(`WebRTC setup failed: ${e.message}`);
            setIsConnecting(false);
            return null;
        }
    };

    // HLS 播放逻辑
    const setupHLS = async () => {
        setIsConnecting(true);
        setError(null);
        const video = videoRef.current;
        if (!video) {
            setIsConnecting(false);
            return null;
        }

        const ready = await waitForManifest(hlsUrl);
        if (!ready) {
            setError('HLS manifest not ready (timeout)');
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
                return {hls};
            } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                video.src = hlsUrl;
                video.play().catch(() => {});
                setIsConnecting(false);
                return {hls: null};
            } else {
                setError('HLS is not supported in this browser');
                setIsConnecting(false);
                return null;
            }
        } catch (e: any) {
            setError(e?.message || 'HLS Playbook failed');
            setIsConnecting(false);
            return null;
        }
    };

    // 统一的播放逻辑
    useEffect(() => {
        let cleanup: (() => void) | null = null;

        const setup = async () => {
            if (streamType === 'webrtc') {
                const result = await setupWebRTC();
                if (result) {
                    cleanup = () => {
                        try {
                            result.peerConnection.close();
                        } catch {}
                    };
                }
            } else {
                const result = await setupHLS();
                if (result && result.hls) {
                    cleanup = () => {
                        try {
                            result.hls!.destroy();
                        } catch {}
                    };
                }
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
    }, [streamType, hlsUrl, webrtcApiUrl]);
    return (
        <Stack>
            <Group>
                <Button 
                    variant={streamType === 'hls' ? 'filled' : 'outline'}
                    onClick={() => setStreamType('hls')}
                    loading={streamType === 'hls' && isConnecting}
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
                style={{width: '100%', background: '#000', minHeight: 300}}
            />
            
            <Group>
                <Text size="xs" c="dimmed">
                    Path: <Badge variant="light">{path}</Badge>
                </Text>
                <Text size="xs" c="dimmed">
                    Mode: <Badge variant="light" color={streamType === 'webrtc' ? 'blue' : 'green'}>
                        {streamType.toUpperCase()}
                    </Badge>
                </Text>
                {streamType === 'webrtc' && (
                    <Text size="xs" c="dimmed">
                        WebRTC: <Badge variant="light" color="orange">localhost:8888</Badge>
                    </Text>
                )}
            </Group>
        </Stack>
    );
}
