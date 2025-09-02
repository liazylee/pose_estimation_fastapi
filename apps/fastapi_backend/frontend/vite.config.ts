import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig(({ mode }) => {
    // 加载当前模式下的 .env 文件
    const env = loadEnv(mode, process.cwd());

    const baseHost = env.VITE_API_BASE
    const wsHost = env.VITE_API_WS
    const hlsHost = env.VITE_API_HLS;
    const webrtcHost = env.VITE_API_WEBRTC;

    return {
        plugins: [react()],
        server: {
            port: 5173,
            host: true,
            proxy: {
                '^/(api|upload|status|result|streams|health|records|media)': {
                    target: baseHost,
                    changeOrigin: true,
                },
                '/whep': webrtcHost,
                '/hls': {
                    target: hlsHost,
                    changeOrigin: true,
                    rewrite: (path) => path.replace(/^\/hls/, '') // 去掉前缀
                },
                '/ws': {
                    target: wsHost,
                    changeOrigin: true,
                    ws: true,
                }
            }
        },
        build: {
            outDir: 'dist',
            emptyOutDir: true,
            rollupOptions: {
                output: {
                    manualChunks: undefined,
                },
            },
        },
        base: '/app/',
        resolve: {
            alias: {
                '@': path.resolve(__dirname, 'src')
            }
        }
    };
});
