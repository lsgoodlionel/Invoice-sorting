/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const BACKEND_ORIGIN = 'http://127.0.0.1:8765';

// 测试里的时间断言按北京时间写；固定时区，避免在其他时区的开发机上失败（子进程继承该变量）
if (process.env.VITEST) process.env.TZ = 'Asia/Shanghai';

export default defineConfig({
  base: '/',
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: BACKEND_ORIGIN, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    coverage: {
      provider: 'v8',
      include: ['src/lib/**/*.ts', 'src/api/**/*.ts'],
      exclude: ['src/**/*.test.ts', 'src/**/*.test.tsx', 'src/api/types.ts'],
      reporter: ['text', 'text-summary'],
    },
  },
});
