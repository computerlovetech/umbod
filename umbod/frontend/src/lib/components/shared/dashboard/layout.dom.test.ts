import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import LayoutFixture from './layout.test-support.svelte';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

function button(label: string): HTMLButtonElement {
  const found = Array.from(document.querySelectorAll('button')).find((candidate): boolean => candidate.textContent === label);
  expect(found).toBeDefined();
  return found!;
}

describe('dashboard layout composition', (): void => {
  it('renders named panels across rows with caller-owned actions and footer', (): void => {
    const refresh = vi.fn<() => void>();
    component = mount(LayoutFixture, { target: document.body, props: { showActions: true, showFooter: true, refresh } });
    flushSync();

    const container = document.querySelector('section[aria-label="Service health"]');
    expect(container).not.toBeNull();
    expect(container!.querySelector('h2')?.textContent).toBe('Service health');
    expect(Array.from(container!.querySelectorAll('h3')).map((heading): string => heading.textContent ?? '')).toEqual(['Daily activity', 'Outcomes', 'Operation mix']);
    expect(container!.querySelector('section[aria-label="Daily activity"]')?.textContent).toContain('Activity visualization');
    expect(container!.querySelector('section[aria-label="Outcomes"]')?.textContent).toContain('Outcome visualization');
    expect(container!.querySelector('section[aria-label="Operation mix"]')?.textContent).toContain('Mix visualization');
    expect(container!.querySelector('time')?.getAttribute('datetime')).toBe('2026-11-30T12:00:00Z');

    button('Refresh dashboard').click();
    button('Refresh activity').click();
    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it('leaves optional container actions and footer absent without hiding panel content', (): void => {
    component = mount(LayoutFixture, { target: document.body, props: { showActions: false, showFooter: false, refresh: (): void => {} } });
    flushSync();

    expect(document.querySelector('time')).toBeNull();
    expect(Array.from(document.querySelectorAll('button')).map((candidate): string => candidate.textContent ?? '')).toEqual(['Refresh activity']);
    expect(document.querySelectorAll('h3')).toHaveLength(3);
  });
});
