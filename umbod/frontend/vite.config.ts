import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [sveltekit()],
  test: {
    projects: [
      {
        extends: true,
        test: {
          name: 'unit',
          include: ['src/**/*.{test,spec}.{js,ts}'],
          exclude: ['src/**/*.dom.test.ts']
        }
      },
      {
        extends: true,
        resolve: { conditions: ['browser'] },
        test: {
          name: 'dom',
          environment: 'happy-dom',
          include: ['src/**/*.dom.test.ts']
        }
      }
    ],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{js,ts,svelte}'],
      exclude: [
        'src/**/*.{test,spec}.{js,ts}',
        'src/**/*.test-support.{js,ts}',
        'src/**/test-fixtures.{js,ts}',
        'src/**/*test-helper.{js,ts}',
        'src/**/*.d.ts'
      ],
      reporter: ['text', 'lcov']
    }
  }
});
