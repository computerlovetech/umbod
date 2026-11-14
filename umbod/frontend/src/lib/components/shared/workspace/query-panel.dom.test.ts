import { afterEach, expect, test, vi } from 'vitest';
import { createRawSnippet, flushSync, mount, tick, unmount } from 'svelte';
import QueryPanel from './QueryPanel.svelte';

let component: ReturnType<typeof mount> | undefined;
afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

function renderPanel(onrun: () => Promise<boolean>, pending: boolean = false, onreset: () => void = (): void => {}): HTMLDetailsElement {
  component = mount(QueryPanel, { target: document.body, props: {
    id: 'test-query', summary: 'Applied query', pending, onrun, onreset,
    children: createRawSnippet(() => ({ render: (): string => '<label>Filter<input name="filter" /></label>' }))
  } });
  flushSync();
  const panel = document.querySelector('details');
  expect(panel).not.toBeNull();
  return panel!;
}

function button(label: string): HTMLButtonElement {
  const found = Array.from(document.querySelectorAll('button')).find((item): boolean => item.textContent?.trim() === label);
  expect(found).toBeDefined();
  return found!;
}

test('starts collapsed, describes the applied query and resets without submitting', async (): Promise<void> => {
  const onrun = vi.fn<() => Promise<boolean>>().mockResolvedValue(true);
  const onreset = vi.fn<() => void>();
  const panel = renderPanel(onrun, false, onreset);
  expect(panel.open).toBe(false);
  expect(panel.querySelector('summary')?.textContent).toContain('Applied query');
  panel.open = true;
  button('Reset').click();
  await tick();
  expect(onreset).toHaveBeenCalledOnce();
  expect(onrun).not.toHaveBeenCalled();
  expect(panel.open).toBe(true);
});

test.each([true, false])('folds and restores summary focus only after successful submission: %s', async (success: boolean): Promise<void> => {
  const onrun = vi.fn<() => Promise<boolean>>().mockResolvedValue(success);
  const panel = renderPanel(onrun);
  panel.open = true;
  const run = button('Run query');
  run.focus();
  run.click();
  await tick();
  expect(onrun).toHaveBeenCalledOnce();
  expect(panel.open).toBe(!success);
  expect(document.activeElement).toBe(success ? panel.querySelector('summary') : run);
});

test('pending queries prevent repeat submissions and reset', async (): Promise<void> => {
  const onrun = vi.fn<() => Promise<boolean>>().mockResolvedValue(true);
  const onreset = vi.fn<() => void>();
  const panel = renderPanel(onrun, true, onreset);
  panel.open = true;
  expect(button('Run query').disabled).toBe(true);
  expect(button('Reset').disabled).toBe(true);
  document.querySelector('form')!.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));
  await tick();
  expect(onrun).not.toHaveBeenCalled();
  expect(onreset).not.toHaveBeenCalled();
});
