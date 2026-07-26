import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    setupFiles: ['./src/test-setup.ts'],
    coverage: {
      reporter: ['html', 'lcov', 'text-summary'],
      thresholds: {
        statements: 85,
        lines: 85,
        functions: 60,
        branches: 65,
      },
    },
  },
});
