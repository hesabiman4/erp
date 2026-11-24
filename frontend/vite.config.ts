import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(({mode})=>{const env=loadEnv(mode,'.','');const target=env.VITE_PROXY_TARGET||'http://127.0.0.1:8000';return { plugins: [react()],build:{rollupOptions:{output:{manualChunks:{vendor:['react','react-dom','react-router-dom','@tanstack/react-query'],i18n:['i18next','react-i18next']}}}}, server: { port: 5173, host:'0.0.0.0', proxy: { '/api': { target, changeOrigin: true }, '/media': { target, changeOrigin: true } } } };});
