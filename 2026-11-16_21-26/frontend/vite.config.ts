import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

// Runtime-only Vue (no template compiler in the bundle): templates are compiled at build time, so the CSP needs
// no 'unsafe-eval'. The dev server proxies the API and print pages to Django.
export default defineConfig({
  plugins: [vue()],
  build: { outDir: 'dist', assetsDir: 'assets', sourcemap: false, target: 'es2022' },
  server: {
    proxy: {
      '/api': { target: process.env.BACKEND_URL ?? 'http://localhost:8000', changeOrigin: false },
      '/print/': { target: process.env.BACKEND_URL ?? 'http://localhost:8000', changeOrigin: false },
      '/health': { target: process.env.BACKEND_URL ?? 'http://localhost:8000', changeOrigin: false },
    },
  },
});
