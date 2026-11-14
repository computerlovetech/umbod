import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['tests/browser/*.safari.test.ts'],
    fileParallelism: false,
    hookTimeout: 90000,
    testTimeout: 30000
  }
});
