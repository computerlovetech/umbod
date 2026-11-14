import { afterEach, expect, test, vi } from 'vitest';
import { createRawSnippet, mount, tick, unmount } from 'svelte';
import ActionMenu from './ActionMenu.svelte';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

test('disabled menu retains its native trigger but cannot open from click or keyboard', async (): Promise<void> => {
  const target = document.createElement('div');
  document.body.append(target);
  const change = vi.fn();
  component = mount(ActionMenu, { target, props: {
    open: true,
    disabled: true,
    label: 'Item actions',
    trigger: createRawSnippet(() => ({ render: (): string => '<span>More</span>' })),
    menu: createRawSnippet(() => ({ render: (): string => '<button role="menuitem">Inspect</button>' })),
    onopenchange: change
  } });
  await tick();
  const trigger = target.querySelector('button');
  expect(trigger).not.toBeNull();
  expect(trigger!.disabled).toBe(true);
  expect(trigger!.getAttribute('aria-expanded')).toBe('false');
  expect(target.querySelector('[role="menu"]')).toBeNull();
  trigger!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  trigger!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
  await tick();
  expect(change).not.toHaveBeenCalled();
  expect(target.querySelector('[role="menu"]')).toBeNull();
});
