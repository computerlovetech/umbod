import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import DashboardPeriodSwitch from './DashboardPeriodSwitch.svelte';
import { VisualizationProps } from './visualizations/visualization-props.test-support.svelte';

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

describe('dashboard period switch', (): void => {
  it('uses two pressed-state buttons and follows the parent-owned selection', (): void => {
    const selection = new VisualizationProps<7 | 30>(7);
    const onchange = vi.fn<(period: 7 | 30) => void>();
    component = mount(DashboardPeriodSwitch, { target: document.body, props: {
      get value(): 7 | 30 { return selection.value; },
      onchange
    } });
    flushSync();

    expect(document.querySelector('[role="group"]')?.getAttribute('aria-label')).toBe('Time period');
    expect(document.querySelectorAll('button')).toHaveLength(2);
    expect(document.querySelector('[role="combobox"]')).toBeNull();
    expect(button('7 days').getAttribute('aria-pressed')).toBe('true');
    expect(button('30 days').getAttribute('aria-pressed')).toBe('false');
    button('30 days').click();
    expect(onchange).toHaveBeenCalledExactlyOnceWith(30);
    expect(button('7 days').getAttribute('aria-pressed')).toBe('true');

    selection.replace(30);
    flushSync();
    expect(button('30 days').getAttribute('aria-pressed')).toBe('true');
    expect(button('7 days').getAttribute('aria-pressed')).toBe('false');
    button('7 days').click();
    expect(onchange).toHaveBeenLastCalledWith(7);
  });
});
