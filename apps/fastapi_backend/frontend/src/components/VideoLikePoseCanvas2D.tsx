// VideoLikePoseCanvas2D.tsx - 模拟视频播放效果
import React, {useCallback, useEffect, useRef, useState} from "react";
import { getDisplayId, getDisplayIdColor, extractDisplayIds, PersonData } from '@/utils/displayId';
import { useGlobalStore } from '@/store/global';

interface DisplayIdInfo {
    id: string;
    displayValue: number;
    label: string;
    type: 'jersey' | 'track';
    confidence: number;
    fallbackTrackId: number;
}

type PoseCanvasProps = {
    frameData: any; // WebSocket数据从父组件传入
    onManualReconnect: () => void;
    selectedDisplayId?: string | null; // Changed from selectedTrackId
    limbColorMode?: "python" | "track";
    targetFps?: number; // 目标播放帧率，默认25fps
    bufferSize?: number; // 缓冲区大小，默认50帧
    onDisplayIdsUpdate?: (displayIds: DisplayIdInfo[]) => void; // Changed from onTrackIdsUpdate
    jerseyConfidenceThreshold?: number;
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

    constructor(targetFps: number) {
        this.targetInterval = 1000 / targetFps;
    }

    shouldPlayNextFrame(): boolean {
        const now = performance.now();
        if (now - this.lastPlayTime >= this.targetInterval) {
            this.lastPlayTime = now;
            return true;
        }
        return false;
    }

    setFps(fps: number): void {
        this.targetInterval = 1000 / fps;
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

// Sports-themed color scheme with better contrast
const DISPLAY_COLORS = [
    "#00C853", // Sports green
    "#FF6F00", // Orange
    "#2196F3", // Blue
    "#E91E63", // Pink
    "#9C27B0", // Purple
    "#FF9800", // Amber
    "#00BCD4", // Cyan
    "#4CAF50", // Green
    "#F44336", // Red
    "#FF5722"  // Deep Orange
];

export default function VideoLikePoseCanvas2D({
                                                  frameData,
                                                  onManualReconnect,
                                                  selectedDisplayId = null,
                                                  limbColorMode = "python",
                                                  targetFps = 25, // 默认25fps播放
                                                  bufferSize = 30,
                                                  onDisplayIdsUpdate,
                                                  jerseyConfidenceThreshold = 0.7
                                              }: PoseCanvasProps) {
    // 视频的宽高比，根据这个比例来设置Canvas
    const aspectRatio = useGlobalStore(s => s.aspectRatio);

    // 流视频是否已暂停
    const isPaused = useGlobalStore(s => s.isPaused);

    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const containerRef = useRef<HTMLDivElement | null>(null);
    const [canvasSize, setCanvasSize] = useState({ width: 640, height: 360 }); // 默认初始值

    const animationRef = useRef<number | null>(null);

    // 帧缓冲和播放控制
    const frameBuffer = useRef(new FrameBuffer(bufferSize));
    const playbackController = useRef(new PlaybackController(targetFps));

    const [bufferLevel, setBufferLevel] = useState(0);
    const [playbackFps, setPlaybackFps] = useState(targetFps);
    const [availableDisplayIds, setAvailableDisplayIds] = useState<DisplayIdInfo[]>([]);

    // 统计信息
    const [stats, setStats] = useState({
        receivedFrames: 0,
        playedFrames: 0,
        droppedFrames: 0,
        realFps: 0
    });

    const fpsCounterRef = useRef({frames: 0, lastTime: performance.now()});

    // 自动根据容器宽度设置 canvas 宽高
    useEffect(() => {
        if (!containerRef.current) return;

        const observer = new ResizeObserver(entries => {
            for (const entry of entries) {
                const width = entry.contentRect.width;
                const height = width / aspectRatio;
                setCanvasSize({ width, height });
            }
        });

        observer.observe(containerRef.current);

        return () => observer.disconnect();
    }, [aspectRatio]);

    // 更新 canvas 元素的实际绘图分辨率（canvas.width / height）
    useEffect(() => {
        const canvas = canvasRef.current;
        if (canvas) {
            canvas.width = canvasSize.width;
            canvas.height = canvasSize.height;
        }
    }, [canvasSize]);

    const transformCoordinate = useCallback((x: number, y: number): [number, number] => {
        const scaleX = canvasSize.width / canvasSize.width; // 通常为 1
        const scaleY = canvasSize.height / canvasSize.height;
        return [x * scaleX, y * scaleY];
    }, [canvasSize]);

    // 绘制单帧
    const drawFrame = useCallback((frameData: FrameData) => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        // 清除画布
        ctx.fillStyle = '#000000';
        ctx.fillRect(0, 0, canvasSize.width, canvasSize.height);

        // 筛选要绘制的人员 - using display IDs
        let targetPersons = frameData.persons;
        if (selectedDisplayId !== null) {
            targetPersons = frameData.persons.filter((p: PersonData) => {
                const displayIdInfo = getDisplayId(p, jerseyConfidenceThreshold);
                return displayIdInfo.id === selectedDisplayId;
            });
        }

        // 收集可用Display IDs
        const currentDisplayIds = extractDisplayIds(frameData.persons, jerseyConfidenceThreshold);
        const displayIdStrings = currentDisplayIds.map(d => d.id).sort();
        const currentIdStrings = availableDisplayIds.map(d => d.id).sort();

        if (JSON.stringify(displayIdStrings) !== JSON.stringify(currentIdStrings)) {
            setAvailableDisplayIds(currentDisplayIds);
            onDisplayIdsUpdate?.(currentDisplayIds);
        }

        // 绘制每个人 - using display IDs
        targetPersons.forEach((person: PersonData) => {
            const displayIdInfo = getDisplayId(person, jerseyConfidenceThreshold);
            const joints: [number, number][] = (person.pose || []).map(joint =>
                Array.isArray(joint) && joint.length >= 2 ? [joint[0], joint[1]] as [number, number] : [0, 0]
            );
            const bbox = person.bbox;
            const speed = typeof person.speed_kmh === "number" ? `${person.speed_kmh.toFixed(1)}km/h` : "";
            const jerseyInfo = displayIdInfo.type === 'jersey' ?
                ` (${Math.round(displayIdInfo.confidence * 100)}%)` : "";

            const color = limbColorMode === "python" ? undefined : getDisplayIdColor(displayIdInfo.id, DISPLAY_COLORS);

            // 设置绘制属性
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.imageSmoothingEnabled = true;

            // 转换关键点坐标
            const transformedJoints = joints.map(([x, y]) => transformCoordinate(x, y));

            // 绘制骨架
            ctx.lineWidth = 3;

            for (const part in PART_CONNECTIONS) {
                const partColor = limbColorMode === "python" ? PART_COLORS[part] : color;
                ctx.strokeStyle = partColor || "#ffffff";

                ctx.beginPath();
                for (const [a, b] of PART_CONNECTIONS[part]) {
                    const A = transformedJoints[a];
                    const B = transformedJoints[b];
                    if (!A || !B) continue;

                    ctx.moveTo(Math.round(A[0]), Math.round(A[1]));
                    ctx.lineTo(Math.round(B[0]), Math.round(B[1]));
                }
                ctx.stroke();
            }

            // 绘制关键点
            for (let j = 0; j < transformedJoints.length; j++) {
                const [x, y] = transformedJoints[j] || [];
                if (x == null || y == null) continue;

                const partColor = limbColorMode === "python" ? PART_COLORS[JOINT_PART[j]] : color;
                ctx.fillStyle = partColor || "#b13434";

                ctx.beginPath();
                ctx.arc(Math.round(x), Math.round(y), 4, 0, 2 * Math.PI);
                ctx.fill();
            }

            // 绘制边界框
            if (bbox && bbox.length === 4) {
                const [x1, y1, x2, y2] = bbox;
                const [tx1, ty1] = transformCoordinate(x1, y1);
                const [tx2, ty2] = transformCoordinate(x2, y2);

                ctx.strokeStyle = color || "#ffffff";
                ctx.lineWidth = 2;
                ctx.setLineDash([8, 4]);
                ctx.strokeRect(Math.round(tx1), Math.round(ty1), Math.round(tx2 - tx1), Math.round(ty2 - ty1));
                ctx.setLineDash([]);

                // 标签 - enhanced with jersey info
                const text = `${displayIdInfo.label}${jerseyInfo}${speed ? " • " + speed : ""}`;
                ctx.font = displayIdInfo.type === 'jersey' ? "bold 14px sans-serif" : "14px sans-serif";
                const textWidth = ctx.measureText(text).width;
                const padding = 8;

                // Different background for jersey vs track
                ctx.fillStyle = displayIdInfo.type === 'jersey' ?
                    (color || "#00C853") : (color || "#ffffff");
                ctx.globalAlpha = displayIdInfo.type === 'jersey' ? 0.9 : 0.8;
                ctx.fillRect(tx1, Math.max(0, ty1 - 30), textWidth + padding * 2, 24);

                ctx.globalAlpha = 1;
                ctx.fillStyle = displayIdInfo.type === 'jersey' ? "#ffffff" : "#000000";
                ctx.fillText(text, tx1 + padding, Math.max(18, ty1 - 10));
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
    }, [selectedDisplayId, limbColorMode, availableDisplayIds, onDisplayIdsUpdate, transformCoordinate, jerseyConfidenceThreshold]);

    // 播放循环
    const playLoop = useCallback(() => {
        if (isPaused) {
            animationRef.current = requestAnimationFrame(playLoop);
            return;
        }

        // 更新缓冲区状态
        const bufferSize = frameBuffer.current.getBufferSize();
        setBufferLevel(bufferSize);

        // 检查是否应该播放下一帧
        if (!isPaused && playbackController.current.shouldPlayNextFrame()) {
            if (frameBuffer.current.hasFrames()) {
                const nextFrame = frameBuffer.current.getNextFrame();
                if (nextFrame) {
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
                        ctx.fillRect(0, 0, canvasSize.width, canvasSize.height);

                        ctx.font = '16px sans-serif';
                        ctx.textAlign = 'left';
                    }
                }
            }
        }
    }, [drawFrame,isPaused]);

    const changeFps = useCallback((fps: number) => {
        playbackController.current.setFps(fps);
        setPlaybackFps(fps);
    }, []);

    // 处理传入的帧数据
    useEffect(() => {
        if (!frameData) return;

        const frame = frameData?.tracked_poses_results ? frameData : frameData?.results?.[0];
        if (!frame) return;

        // 添加到缓冲区而不是立即渲染
        frameBuffer.current.addFrame(frame);

        setStats(prev => ({
            ...prev,
            receivedFrames: prev.receivedFrames + 1
        }));
    }, [frameData]);

    // 清空缓冲区的处理函数
    const handleClearBuffer = useCallback(() => {
        frameBuffer.current.clear();
        setStats(prev => ({ ...prev, receivedFrames: 0, playedFrames: 0 }));
        onManualReconnect();
    }, [onManualReconnect]);

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
        <div ref={containerRef} style={{ position: "relative", width: "100%" }}>
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
                    borderRadius: "4px",
                    zIndex: 10,
                    fontSize: "12px",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center"
                }}
            >
                <div style={{display: "flex", gap: "12px", alignItems: "center"}}>
                    <div>FPS:
                        <select
                            value={playbackFps}
                            onChange={(e) => changeFps(Number(e.target.value))}
                            style={{
                                marginLeft: "4px",
                                background: "#333",
                                color: "#fff",
                                border: "1px solid #555",
                                borderRadius: "4px"
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

                    {/* 重播按钮 */}
                    <button
                        onClick={handleClearBuffer}
                        style={{
                            background: "#4444ff",
                            border: "none",
                            color: "#fff",
                            padding: "4px 8px",
                            borderRadius: "4px",
                            fontSize: "11px",
                            cursor: "pointer"
                        }}
                        title="重新播放 - 清空缓冲区并重新获取数据"
                    >
                        🔄 Replay
                    </button>
                </div>

                <div style={{display: "flex", gap: "12px", fontSize: "11px"}}>
                    <span>📡 {stats.receivedFrames}</span>
                    <span>▶ {stats.playedFrames}</span>
                    <span>⚡ {stats.realFps}fps</span>
                    {selectedDisplayId && (
                        <span>🎯 {availableDisplayIds.find(d => d.id === selectedDisplayId)?.label || 'Unknown'}</span>
                    )}
                </div>
            </div>

            <canvas
                ref={canvasRef}
                style={{
                    width: '100%',
                    height: `${canvasSize.height}px`,
                    display: 'block',
                    imageRendering: 'auto',
                    borderRadius: '4px',
                    cursor: 'pointer'
                }}
            />
        </div>
    );
}
