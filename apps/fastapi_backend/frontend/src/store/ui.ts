import { create } from 'zustand';

type UIState = {
  activeRequests: number;
  increment: () => void;
  decrement: () => void;
};

export const useUIStore = create<UIState>((set) => ({
  activeRequests: 0,
  increment: () => set((s) => ({ activeRequests: s.activeRequests + 1 })),
  decrement: () => set((s) => ({ activeRequests: Math.max(0, s.activeRequests - 1) })),
}));


