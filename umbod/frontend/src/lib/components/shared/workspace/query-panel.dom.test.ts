import { afterEach, expect, test, vi } from 'vitest';
import { createRawSnippet, flushSync, mount, tick, unmount } from 'svelte';
import QueryPanel from './QueryPanel.svelte';

let component: ReturnType<typeof mount> | undefined;
afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

function renderPanel(onrun: () => Promise<boolean>, pending: boolean = false, onreset: () => void = (): void => {}): HTMLButtonElement {
  component = mount(QueryPanel, { target: document.body, props: {
    id: 'test-query', summary: 'Applied query', pending, onrun, onreset,
    children: createRawSnippet(() => ({ render: (): string => '<label>Filter<input name="filter" /></label>' }))
  } });
  flushSync();
  const trigger = document.querySelector<HTMLButtonElement>('button[aria-expanded]');
  if (!trigger) throw new Error('Query trigger not found');
  return trigger;
}

function button(label: string): HTMLButtonElement {
  const found = Array.from(document.querySelectorAll('button')).find((item): boolean => item.textContent?.trim() === label);
  expect(found).toBeDefined();
  return found!;
}

test('starts collapsed, describes the applied query and resets without submitting', async (): Promise<void> => {
  const onrun = vi.fn<() => Promise<boolean>>().mockResolvedValue(true);
  const onreset = vi.fn<() => void>();
  const trigger = renderPanel(onrun, false, onreset);
  expect(trigger.getAttribute('aria-expanded')).toBe('false');
  expect(trigger.textContent).toContain('Applied query');
  trigger.click();
  await tick();
  button('Reset').click();
  await tick();
  expect(onreset).toHaveBeenCalledOnce();
  expect(onrun).not.toHaveBeenCalled();
  expect(trigger.getAttribute('aria-expanded')).toBe('true');
});

test.each([true, false])('folds and restores trigger focus only after successful submission: %s', async (success: boolean): Promise<void> => {
  const onrun = vi.fn<() => Promise<boolean>>().mockResolvedValue(success);
  const trigger = renderPanel(onrun);
  trigger.click();
  await tick();
  const run = button('Run query');
  run.focus();
  run.click();
  await vi.waitFor(() => expect(onrun).toHaveBeenCalledOnce());
  await vi.waitFor(() => expect(trigger.getAttribute('aria-expanded')).toBe(String(!success)));
  expect(document.activeElement).toBe(success ? trigger : run);
});

test('pending queries prevent repeat submissions and reset', async (): Promise<void> => {
  const onrun = vi.fn<() => Promise<boolean>>().mockResolvedValue(true);
  const onreset = vi.fn<() => void>();
  const trigger = renderPanel(onrun, true, onreset);
  trigger.click();
  await tick();
  expect(button('Run query').disabled).toBe(true);
  expect(button('Reset').disabled).toBe(true);
  document.querySelector('form')!.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));
  await tick();
  expect(onrun).not.toHaveBeenCalled();
  expect(onreset).not.toHaveBeenCalled();
});
