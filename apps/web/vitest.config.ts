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
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      reportsDirectory: './coverage',
      exclude: [
        'node_modules/**',
        '.next/**',
        '**/*.test.{ts,tsx}',
        '**/__tests__/**',
        'vitest.setup.tsx',
        'e2e/**',
        'scripts/**',
      ],
    },
  },
  resolve: {
    alias: {
      '@/design-system': path.resolve(import.meta.dirname, './src/design-system'),
      '@/holographic': path.resolve(import.meta.dirname, './src/holographic'),
      '@': path.resolve(import.meta.dirname, './'),
    },
  },
});
