import { useEffect, useMemo, useRef, useState } from 'react';
import Hls from 'hls.js';
import { Alert, Button, Group, SegmentedControl, Stack, Text } from '@mantine/core';

type Props = {
  path: string; // stream path e.g. outstream_<task_id>
};

export default function MediaPlayer({ path }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const [mode, setMode] = useState<'webrtc' | 'hls'>('webrtc');
  const [error, setError] = useState<string | null>(null);

  const whepUrl = useMemo(() => `${location.protocol}//${location.host}/whep/${path}`, [path]);
  const hlsUrl = useMemo(() => `${location.protocol}//${location.host}/hls/${path}/index.m3u8`, [path]);

  useEffect(() => {
    setError(null);
    if (!videoRef.current) return;

    if (mode === 'webrtc') {
      // Cleanup any HLS instance
      if (Hls.isSupported()) {
        const v = videoRef.current as HTMLVideoElement;
        if (v) {
          try { v.pause(); v.removeAttribute('src'); v.load(); } catch {}
        }
      }

      const pc = new RTCPeerConnection();
      pcRef.current = pc;
      pc.addTransceiver('video', { direction: 'recvonly' });
      pc.ontrack = (e) => {
        if (videoRef.current) {
          videoRef.current.srcObject = e.streams[0];
          videoRef.current.play().catch(() => {});
        }
      };
      pc.onconnectionstatechange = () => {
        if (pc.connectionState === 'failed') setError('WebRTC 连接失败');
      };
      (async () => {
        try {
          const offer = await pc.createOffer();
          await pc.setLocalDescription(offer);
          const res = await fetch(whepUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/sdp' },
            body: offer.sdp,
          });
          if (!res.ok) throw new Error(`WHEP ${res.status}`);
          const answerSdp = await res.text();
          await pc.setRemoteDescription({ type: 'answer', sdp: answerSdp });
        } catch (e: any) {
          setError(e?.message || 'WebRTC 播放失败');
        }
      })();

      return () => {
        pc.getSenders().forEach((s) => s.track?.stop());
        pc.close();
        pcRef.current = null;
        if (videoRef.current) {
          videoRef.current.srcObject = null;
        }
      };
    } else {
      // HLS fallback
      try {
        if (Hls.isSupported()) {
          const hls = new Hls({ lowLatencyMode: true });
          hls.loadSource(hlsUrl);
          hls.attachMedia(videoRef.current);
          hls.on(Hls.Events.ERROR, (_e, data) => {
            if (data.fatal) setError('HLS 播放失败');
          });
          return () => {
            hls.destroy();
          };
        } else if (videoRef.current?.canPlayType('application/vnd.apple.mpegurl')) {
          // Safari native HLS
          videoRef.current.src = hlsUrl;
          videoRef.current.play().catch(() => {});
          return () => {
            if (videoRef.current) {
              try { videoRef.current.pause(); } catch {}
            }
          };
        } else {
          setError('浏览器不支持 HLS');
        }
      } catch (e: any) {
        setError(e?.message || 'HLS 播放失败');
      }
    }
  }, [mode, whepUrl, hlsUrl]);

  return (
    <Stack>
      <Group justify="space-between">
        <SegmentedControl value={mode} onChange={(v: any) => setMode(v)} data={[
          { label: 'WebRTC(低延迟)', value: 'webrtc' },
          { label: 'HLS(兼容)', value: 'hls' },
        ]} />
        <Button variant="light" onClick={() => setMode(mode === 'webrtc' ? 'hls' : 'webrtc')}>切换</Button>
      </Group>
      {error && <Alert color="red">{error}</Alert>}
      <video ref={videoRef} playsInline controls style={{ width: '100%', background: '#000', minHeight: 300 }} />
      <Text size="xs" c="dimmed">路径: {path}</Text>
    </Stack>
  );
}


