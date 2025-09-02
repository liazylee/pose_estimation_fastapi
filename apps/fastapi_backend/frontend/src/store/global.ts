import { create } from 'zustand';

interface GlobalState {
    // m3u8 是否就绪
    isM3u8Ready: boolean;
    setM3u8Ready: (ready: boolean) => void;
    // 视频宽高比
    aspectRatio: number;
    setAspectRatio: (ratio: number) => void;
    // 视频总时长，秒为单位，null表示未知
    videoDuration: number | null;
    setVideoDuration: (duration: number) => void;
    // canvas和图表暂停播放
    isPaused: boolean;
    setPaused: (paused: boolean) => void;
}

export const useGlobalStore = create<GlobalState>((set) => ({
    isM3u8Ready: false,
    setM3u8Ready: (ready) => set({ isM3u8Ready: ready }),

    aspectRatio: 16 / 9,
    setAspectRatio: (ratio) => set({ aspectRatio: ratio }),

    videoDuration: null,
    setVideoDuration: (duration) => set({ videoDuration: duration }),

    isPaused: false,
    setPaused: (paused) => set({ isPaused: paused})
}));
