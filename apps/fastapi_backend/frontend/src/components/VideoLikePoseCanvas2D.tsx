// VideoLikePoseCanvas2D.tsx - 模拟视频播放效果
import React, {useCallback, useEffect, useRef, useState} from "react";

type PoseCanvasProps = {
    wsUrl: string;
    width: number;
    height: number;
    selectedTrackId?: number | null;
    showSkeleton?: boolean;
    showJoints?: boolean;
    showBBoxes?: boolean;
    limbColorMode?: "python" | "track";
    showDebug?: boolean;
    targetFps?: number; // 目标播放帧率，默认25fps
    bufferSize?: number; // 缓冲区大小，默认50帧
    onTrackIdsUpdate?: (trackIds: number[]) => void;
};

// 帧数据结构
interface FrameData {
    timestamp: number;
    persons: any[];
    frameIndex: number;
}

// 帧缓冲区管理
class FrameBuffer {
    private buffer: FrameData[] = [];
    private maxSize: number;
    private frameCounter = 0;

    constructor(maxSize: number = 50) {
        this.maxSize = maxSize;
    }

    addFrame(data: any): void {
        const frame: FrameData = {
            timestamp: performance.now(),
            persons: data.tracked_poses_results || [],
            frameIndex: this.frameCounter++
        };

        this.buffer.push(frame);

        // 保持缓冲区大小
        if (this.buffer.length > this.maxSize) {
            this.buffer.shift();
        }
    }

    getNextFrame(): FrameData | null {
        return this.buffer.shift() || null;
    }

    getBufferSize(): number {
        return this.buffer.length;
    }

    clear(): void {
        this.buffer = [];
    }

    hasFrames(): boolean {
        return this.buffer.length > 0;
    }
}

// 播放控制器
class PlaybackController {
    private targetInterval: number;
    private lastPlayTime = 0;
    private isPlaying = true;

    constructor(targetFps: number) {
        this.targetInterval = 1000 / targetFps;
    }

    shouldPlayNextFrame(): boolean {
        const now = performance.now();
        if (now - this.lastPlayTime >= this.targetInterval) {
            this.lastPlayTime = now;
            return this.isPlaying;
        }
        return false;
    }

    play(): void {
        this.isPlaying = true;
    }

    pause(): void {
        this.isPlaying = false;
    }

    setFps(fps: number): void {
        this.targetInterval = 1000 / fps;
    }

    isActive(): boolean {
        return this.isPlaying;
    }
}

const PART_CONNECTIONS: Record<string, [number, number][]> = {
    head: [[0, 1], [0, 2], [1, 3], [2, 4]],
    torso: [[5, 11], [6, 12], [11, 12]],
    left_arm: [[5, 7], [7, 9]],
    right_arm: [[6, 8], [8, 10]],
    left_leg: [[11, 13], [13, 15]],
    right_leg: [[12, 14], [14, 16]],
};

const PART_COLORS: Record<string, string> = {
    left_arm: "#0080ff",
    right_arm: "#ffa500",
    left_leg: "#00ffff",
    right_leg: "#ff00ff",
    torso: "#ffff00",
    head: "#ffffff",
};

const JOINT_PART: Record<number, string> = (() => {
    const m: Record<number, string> = {};
    for (const part in PART_CONNECTIONS) {
        for (const [a, b] of PART_CONNECTIONS[part]) {
            if (m[a] === undefined) m[a] = part;
            if (m[b] === undefined) m[b] = part;
        }
    }
    return m;
})();

const TRACK_COLORS = ["#00ffff", "#ff00ff", "#ffff00", "#800080", "#ffa500", "#0080ff"];
const getTrackColor = (id: number) => TRACK_COLORS[Math.abs(id) % TRACK_COLORS.length];

export default function VideoLikePoseCanvas2D({
                                                  wsUrl,
                                                  width,
                                                  height,
                                                  selectedTrackId = null,
                                                  showSkeleton = true,
                                                  showJoints = true,
                                                  showBBoxes = true,
                                                  limbColorMode = "python",
                                                  showDebug = false,
                                                  targetFps = 25, // 默认25fps播放
                                                  bufferSize = 50,
                                                  onTrackIdsUpdate
                                              }: PoseCanvasProps) {
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const animationRef = useRef<number | null>(null);

    // 帧缓冲和播放控制
    const frameBuffer = useRef(new FrameBuffer(bufferSize));
    const playbackController = useRef(new PlaybackController(targetFps));

    const [isPlaying, setIsPlaying] = useState(true);
    const [bufferLevel, setBufferLevel] = useState(0);
    const [playbackFps, setPlaybackFps] = useState(targetFps);
    const [currentFrame, setCurrentFrame] = useState<FrameData | null>(null);
    const [availableTrackIds, setAvailableTrackIds] = useState<number[]>([]);

    // 统计信息
    const [stats, setStats] = useState({
        receivedFrames: 0,
        playedFrames: 0,
        droppedFrames: 0,
        realFps: 0
    });

    const fpsCounterRef = useRef({frames: 0, lastTime: performance.now()});

    // 绘制单帧
    const drawFrame = useCallback((frameData: FrameData) => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        // 清除画布
        ctx.fillStyle = '#000000';
        ctx.fillRect(0, 0, width, height);

        // 筛选要绘制的人员
        let targetPersons = frameData.persons;
        if (selectedTrackId !== null) {
            targetPersons = frameData.persons.filter(p => {
                const trackId = p.track_id ?? 0;
                return trackId === selectedTrackId;
            });
        }

        // 收集可用Track IDs
        const currentTrackIds = frameData.persons
            .map(p => p.track_id ?? 0)
            .filter(id => id > 0);

        if (JSON.stringify(currentTrackIds) !== JSON.stringify(availableTrackIds)) {
            setAvailableTrackIds(currentTrackIds);
            onTrackIdsUpdate?.(currentTrackIds);
        }

        // 绘制每个人
        targetPersons.forEach((person, index) => {
            const trackId = person.track_id ?? index + 1;
            const joints: [number, number][] = person.pose || [];
            const bbox = person.bbox;
            const speed = typeof person.speed_kmh === "number" ? `${person.speed_kmh.toFixed(1)}km/h` : "";

            const color = limbColorMode === "python" ? undefined : getTrackColor(trackId);

            // 设置绘制属性
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.imageSmoothingEnabled = true;

            // 绘制骨架
            if (showSkeleton) {
                ctx.lineWidth = 3;

                for (const part in PART_CONNECTIONS) {
                    const partColor = limbColorMode === "python" ? PART_COLORS[part] : color;
                    ctx.strokeStyle = partColor || "#ffffff";

                    ctx.beginPath();
                    for (const [a, b] of PART_CONNECTIONS[part]) {
                        const A = joints[a];
                        const B = joints[b];
                        if (!A || !B) continue;

                        ctx.moveTo(Math.round(A[0]), Math.round(A[1]));
                        ctx.lineTo(Math.round(B[0]), Math.round(B[1]));
                    }
                    ctx.stroke();
                }
            }

            // 绘制关键点
            if (showJoints) {
                for (let j = 0; j < joints.length; j++) {
                    const [x, y] = joints[j] || [];
                    if (x == null || y == null) continue;

                    const partColor = limbColorMode === "python" ? PART_COLORS[JOINT_PART[j]] : color;
                    ctx.fillStyle = partColor || "#b13434";

                    ctx.beginPath();
                    ctx.arc(Math.round(x), Math.round(y), 4, 0, 2 * Math.PI);
                    ctx.fill();
                }
            }

            // 绘制边界框
            if (showBBoxes && bbox && bbox.length === 4) {
                const [x1, y1, x2, y2] = bbox;

                ctx.strokeStyle = color || "#ffffff";
                ctx.lineWidth = 2;
                ctx.setLineDash([8, 4]);
                ctx.strokeRect(Math.round(x1), Math.round(y1), Math.round(x2 - x1), Math.round(y2 - y1));
                ctx.setLineDash([]);

                // 标签
                const text = `Track ${trackId}${speed ? " • " + speed : ""}`;
                ctx.font = "14px sans-serif";
                const textWidth = ctx.measureText(text).width;
                const padding = 8;

                ctx.fillStyle = color || "#ffffff";
                ctx.globalAlpha = 0.8;
                ctx.fillRect(x1, Math.max(0, y1 - 30), textWidth + padding * 2, 24);

                ctx.globalAlpha = 1;
                ctx.fillStyle = "#000000";
                ctx.fillText(text, x1 + padding, Math.max(18, y1 - 10));
            }
        });

        // 更新FPS统计
        const now = performance.now();
        const counter = fpsCounterRef.current;
        counter.frames++;
        if (now - counter.lastTime >= 1000) {
            const realFps = Math.round(counter.frames * 1000 / (now - counter.lastTime));
            setStats(prev => ({...prev, realFps}));
            counter.frames = 0;
            counter.lastTime = now;
        }

    }, [width, height, selectedTrackId, showSkeleton, showJoints, showBBoxes, limbColorMode, availableTrackIds, onTrackIdsUpdate]);

    // 播放循环
    const playLoop = useCallback(() => {
        // 更新缓冲区状态
        const bufferSize = frameBuffer.current.getBufferSize();
        setBufferLevel(bufferSize);

        // 检查是否应该播放下一帧
        if (playbackController.current.shouldPlayNextFrame()) {
            if (frameBuffer.current.hasFrames()) {
                const nextFrame = frameBuffer.current.getNextFrame();
                if (nextFrame) {
                    setCurrentFrame(nextFrame);
                    drawFrame(nextFrame);
                    setStats(prev => ({
                        ...prev,
                        playedFrames: prev.playedFrames + 1
                    }));
                }
            } else {
                // 缓冲区空了，显示等待状态
                const canvas = canvasRef.current;
                if (canvas) {
                    const ctx = canvas.getContext("2d");
                    if (ctx) {
                        ctx.fillStyle = '#111';
                        ctx.fillRect(0, 0, width, height);

                        ctx.fillStyle = '#666';
                        ctx.font = '16px sans-serif';
                        ctx.textAlign = 'center';
                        ctx.fillText('Buffering...', width / 2, height / 2);
                        ctx.textAlign = 'left';
                    }
                }
            }
        }

        animationRef.current = requestAnimationFrame(playLoop);
    }, [drawFrame, width, height]);

    // 播放控制函数
    const togglePlayback = useCallback(() => {
        if (isPlaying) {
            playbackController.current.pause();
            setIsPlaying(false);
        } else {
            playbackController.current.play();
            setIsPlaying(true);
        }
    }, [isPlaying]);

    const changeFps = useCallback((fps: number) => {
        playbackController.current.setFps(fps);
        setPlaybackFps(fps);
    }, []);

    // WebSocket 数据接收
    useEffect(() => {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onmessage = (evt) => {
            try {
                const data = JSON.parse(evt.data);
                const frame = data?.tracked_poses_results ? data : data?.results?.[0];
                if (!frame) return;

                // 添加到缓冲区而不是立即渲染
                frameBuffer.current.addFrame(frame);

                setStats(prev => ({
                    ...prev,
                    receivedFrames: prev.receivedFrames + 1
                }));

            } catch (e) {
                console.warn("Failed to parse WS:", e);
            }
        };

        return () => {
            ws.close();
        };
    }, [wsUrl]);

    // 启动播放循环
    useEffect(() => {
        animationRef.current = requestAnimationFrame(playLoop);
        return () => {
            if (animationRef.current) {
                cancelAnimationFrame(animationRef.current);
            }
        };
    }, [playLoop]);

    // 更新播放器FPS
    useEffect(() => {
        changeFps(targetFps);
    }, [targetFps, changeFps]);

    return (
        <div style={{position: "relative"}}>
            {/* 播放控制器 */}
            <div
                style={{
                    position: "absolute",
                    bottom: 8,
                    left: 8,
                    right: 8,
                    background: "rgba(0, 0, 0, 0.8)",
                    color: "#fff",
                    padding: "8px 12px",
                    borderRadius: "6px",
                    zIndex: 10,
                    fontSize: "12px",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center"
                }}
            >
                <div style={{display: "flex", gap: "12px", alignItems: "center"}}>
                    <button
                        onClick={togglePlayback}
                        style={{
                            background: isPlaying ? "#ff4444" : "#44ff44",
                            border: "none",
                            color: "#000",
                            padding: "4px 8px",
                            borderRadius: "3px",
                            fontSize: "11px",
                            cursor: "pointer"
                        }}
                    >
                        {isPlaying ? "⏸ Pause" : "▶ Play"}
                    </button>

                    <div>FPS:
                        <select
                            value={playbackFps}
                            onChange={(e) => changeFps(Number(e.target.value))}
                            style={{
                                marginLeft: "4px",
                                background: "#333",
                                color: "#fff",
                                border: "1px solid #555",
                                borderRadius: "2px"
                            }}
                        >
                            <option value={15}>15</option>
                            <option value={20}>20</option>
                            <option value={25}>25</option>
                            <option value={30}>30</option>
                            <option value={50}>50</option>
                        </select>
                    </div>

                    <div>Buffer: {bufferLevel}/{bufferSize}</div>
                </div>

                <div style={{display: "flex", gap: "12px", fontSize: "11px"}}>
                    <span>📡 {stats.receivedFrames}</span>
                    <span>▶ {stats.playedFrames}</span>
                    <span>⚡ {stats.realFps}fps</span>
                    {selectedTrackId && <span>🎯 Track {selectedTrackId}</span>}
                </div>
            </div>

            {/* 调试信息 */}
            {showDebug && (
                <div
                    style={{
                        position: "absolute",
                        top: 8,
                        left: 8,
                        background: "rgba(0, 0, 0, 0.85)",
                        color: "#00ff00",
                        padding: "10px 14px",
                        fontSize: "12px",
                        fontFamily: "monospace",
                        zIndex: 10,
                        borderRadius: "6px",
                        lineHeight: 1.5
                    }}
                >
                    <div>🎬 Mode: {isPlaying ? "Playing" : "Paused"}</div>
                    <div>🎯 Track: {selectedTrackId ?? "All"}</div>
                    <div>📊 Target: {playbackFps}fps</div>
                    <div>📐 {width}×{height}</div>
                    <div>🔍 Available: [{availableTrackIds.join(", ")}]</div>
                    <div>Frame: {currentFrame?.frameIndex ?? "-"}</div>
                </div>
            )}

            <canvas
                ref={canvasRef}
                width={width}
                height={height}
                style={{
                    display: 'block',
                    imageRendering: 'auto',
                    border: isPlaying ? '2px solid #00ff00' : '2px solid #ff4444',
                    borderRadius: '4px',
                    cursor: 'pointer'
                }}
                onClick={togglePlayback}
            />
        </div>
    );
}