import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Dev and the Cloudflare tunnel serve the app under /bot/webapp/; the
  // production image serves it at the root of its own domain.
  base: process.env.VITE_BASE_PATH || '/bot/webapp/',
  server: {
    allowedHosts: ['.trycloudflare.com'],
    proxy: {
      '/api': process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
      '/media': process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
    },
  },
});
