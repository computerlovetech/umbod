import { afterEach, expect, test, vi } from 'vitest';
import { mount, tick, unmount, type ComponentProps } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';
import type ModalShell from './ModalShell.svelte';
import Harness from './modal-shell.test-support.svelte';

type ModalProps = Omit<ComponentProps<typeof ModalShell>, 'children'>;
let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

async function setup(initial: Partial<ModalProps> = {}): Promise<{
  close: ReturnType<typeof vi.fn>;
  submit: ReturnType<typeof vi.fn>;
  update: (next: Partial<ModalProps>) => Promise<void>;
}> {
  const close = vi.fn();
  const submit = vi.fn();
  const props = new SvelteMap<string, ModalProps>([['current', {
    title: 'Edit item', titleId: 'modal-title', descriptionId: 'modal-description', close, ...initial
  }]]);
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(Harness, { target, props: { current: (): ModalProps => props.get('current')!, submit } });
  await tick();
  return {
    close,
    submit,
    update: async (next: Partial<ModalProps>): Promise<void> => {
      props.set('current', { ...props.get('current')!, ...next });
      await tick();
    }
  };
}

function dialog(): HTMLDialogElement {
  const element = document.querySelector('dialog');
  if (!element) throw new Error('Expected mounted dialog');
  return element;
}

function closeButton(): HTMLButtonElement {
  const element = dialog().querySelector<HTMLButtonElement>('button[aria-label="Close"]');
  if (!element) throw new Error('Expected close button');
  return element;
}

test('opens a labelled native modal with an accessible header cross that cancels without submitting', async (): Promise<void> => {
  const view = await setup();
  expect(dialog().open).toBe(true);
  expect(dialog().getAttribute('aria-labelledby')).toBe('modal-title');
  expect(document.getElementById('modal-title')?.textContent).toBe('Edit item');
  expect(dialog().getAttribute('aria-describedby')).toBe('modal-description');
  expect(closeButton().closest('header')).not.toBeNull();
  expect(closeButton().querySelector('svg[aria-hidden="true"]')).not.toBeNull();
  expect(closeButton().type).toBe('button');
  expect(document.activeElement).toBe(dialog().querySelector('[data-dialog-cancel]'));
  closeButton().click();
  expect(view.close).toHaveBeenCalledOnce();
  expect(view.submit).not.toHaveBeenCalled();
});

test('blocks cross, backdrop and native cancellation while pending and responds to updated guards', async (): Promise<void> => {
  const view = await setup({ closeDisabled: true });
  expect(closeButton().disabled).toBe(true);
  closeButton().click();
  dialog().dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: -10, clientY: -10 }));
  const blocked = new Event('cancel', { cancelable: true });
  dialog().dispatchEvent(blocked);
  expect(blocked.defaultPrevented).toBe(true);
  expect(dialog().open).toBe(true);
  expect(view.close).not.toHaveBeenCalled();
  await view.update({ closeDisabled: false });
  expect(closeButton().disabled).toBe(false);
  const allowed = new Event('cancel', { cancelable: true });
  dialog().dispatchEvent(allowed);
  expect(allowed.defaultPrevented).toBe(true);
  expect(dialog().open).toBe(false);
  expect(view.close).toHaveBeenCalledOnce();
});

test('ignores content and surface clicks but dismisses an outside backdrop click', async (): Promise<void> => {
  const view = await setup();
  vi.spyOn(dialog(), 'getBoundingClientRect').mockReturnValue(new DOMRect(10, 10, 200, 200));
  document.getElementById('modal-description')!.click();
  dialog().dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 20, clientY: 20 }));
  expect(view.close).not.toHaveBeenCalled();
  dialog().dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 0, clientY: 0 }));
  expect(view.close).toHaveBeenCalledOnce();
});

test('preserves alert-dialog semantics and caller-selected initial focus', async (): Promise<void> => {
  await setup({ role: 'alertdialog', initialFocus: 'input' });
  expect(dialog().getAttribute('role')).toBe('alertdialog');
  expect(document.activeElement).toBe(dialog().querySelector('input'));
});
