import { create } from 'zustand';

interface GlobalState {
    isM3u8Ready: boolean;
    setM3u8Ready: (ready: boolean) => void;
}

export const useGlobalStore = create<GlobalState>((set) => ({
    isM3u8Ready: false,
    setM3u8Ready: (ready) => set({ isM3u8Ready: ready }),
}));
