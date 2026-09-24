import { readFileSync } from 'node:fs';
import { render } from 'svelte/server';
import { describe, expect, test } from 'vitest';
import ToastRegion from './ToastRegion.svelte';
import { ToastState } from './toast-state.svelte';

describe('ToastRegion', () => {
  test('renders variant text, dismiss controls, and appropriate live semantics', () => {
    const state = new ToastState();
    state.success('Configuration saved');
    state.warning('Connection is slow');
    state.error('Connection failed');

    const { body } = render(ToastRegion, { props: { state } });

    expect(body).toContain('aria-label="Notifications"');
    expect(body).toContain('Success');
    expect(body).toContain('Warning');
    expect(body).toContain('Error');
    expect(body).toMatch(/role="status" aria-live="polite"/);
    expect(body).toMatch(/role="alert" aria-live="assertive"/);
    expect(body).toContain('aria-label="Dismiss success notification"');
    expect(body).toContain('aria-label="Dismiss warning notification"');
    expect(body).toContain('aria-label="Dismiss error notification"');
  });

  test('uses a fixed responsive overlay with stacking and reduced motion support', () => {
    const source = readFileSync(new URL('./ToastRegion.svelte', import.meta.url), 'utf8');

    expect(source).toContain('position: fixed');
    expect(source).toContain('z-index: 10000');
    expect(source).toContain('flex-direction: column');
    expect(source).toContain('width: min(24rem, calc(100vw - 2rem))');
    expect(source).toContain('@media (max-width: 30rem)');
    expect(source).toContain('@media (prefers-reduced-motion: reduce)');
    expect(source).toContain('.toast { animation: none; }');
  });
});
