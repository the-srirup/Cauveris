import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.tsx'],
    include: [
      'components/__tests__/**/*.test.tsx',
      'src/**/__tests__/**/*.test.ts*',
      'lib/__tests__/**/*.test.ts*',
    ],
    pool: 'forks',
    forks: {
      isolate: false,
      singleFork: true,
    },
  },
  resolve: {
    alias: {
      '@/holographic': path.resolve(import.meta.dirname, './src/holographic'),
      '@': path.resolve(import.meta.dirname, './'),
    },
  },
});
