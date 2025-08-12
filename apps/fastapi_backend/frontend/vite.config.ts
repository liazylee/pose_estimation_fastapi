// frontend/vite.config.ts - 修复版本
import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
    plugins: [react()], // 添加 React 插件
    server: {
        port: 5173,
        host: true,
        proxy: {
            '/api': 'http://localhost:8000',
            '/upload': 'http://localhost:8000',
            '/status': 'http://localhost:8000',
            '/result': 'http://localhost:8000',
            '/streams': 'http://localhost:8000',
            // MediaMTX services
            '/whep': 'http://localhost:8889',
            '/hls': 'http://localhost:8888',
            '/ws': {
                target: 'ws://localhost:8000',
                ws: true
            }
        }
    },
    build: {
        outDir: 'dist',
        emptyOutDir: true,
        // 确保生成正确的静态文件
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
});