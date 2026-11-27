import { afterEach, expect, test, vi } from 'vitest';
import { createRawSnippet, mount, tick, unmount, type ComponentProps } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';
import Disclosure from './Disclosure.svelte';
import { openFromParentEffect } from './disclosure.test-support.svelte';

const components: ReturnType<typeof mount>[] = [];

afterEach(async (): Promise<void> => {
  await Promise.all(components.splice(0).map((component) => unmount(component)));
  document.body.replaceChildren();
});

function renderDisclosure(
  target: HTMLElement,
  name: string,
  options: Pick<ComponentProps<typeof Disclosure>, 'initiallyOpen' | 'onOpenChange' | 'expanded'> = {}
): ReturnType<typeof Disclosure> {
  const disclosure = mount(Disclosure, { target, props: {
    ...options,
    get expanded(): boolean | undefined { return options.expanded; },
    label: createRawSnippet(() => ({ render: (): string => `<span>${name}</span>` })),
    children: createRawSnippet<[() => void]>((collapse) => ({
      render: (): string => '<div><input aria-label="Draft" /><button type="button">Done</button></div>',
      setup: (element): (() => void) => {
        const button = element.querySelector('button');
        if (!button) throw new Error('Missing Done button');
        const close = (): void => collapse()();
        button.addEventListener('click', close);
        return (): void => button.removeEventListener('click', close);
      }
    }))
  } });
  components.push(disclosure);
  return disclosure;
}

function findTrigger(name: string): HTMLButtonElement {
  const trigger = [...document.querySelectorAll<HTMLButtonElement>('button[aria-controls]')].find((button) => button.textContent?.trim() === name);
  if (!trigger) throw new Error(`Missing disclosure trigger: ${name}`);
  return trigger;
}

function controlledPanel(trigger: HTMLButtonElement): HTMLElement {
  const id = trigger.getAttribute('aria-controls');
  const panel = id && document.getElementById(id);
  if (!panel) throw new Error('Missing controlled panel');
  return panel;
}

test('starts closed, opens independently and never submits its surrounding form', async (): Promise<void> => {
  const submit = vi.fn((event: Event): void => event.preventDefault());
  const form = document.createElement('form');
  form.addEventListener('submit', submit);
  document.body.append(form);
  renderDisclosure(form, 'First');
  renderDisclosure(form, 'Second');
  await tick();

  const first = findTrigger('First');
  const second = findTrigger('Second');
  expect(first.type).toBe('button');
  expect(first.getAttribute('aria-expanded')).toBe('false');
  expect(second.getAttribute('aria-expanded')).toBe('false');
  expect(controlledPanel(first).id).not.toBe(controlledPanel(second).id);
  expect(controlledPanel(first).hidden).toBe(true);
  expect(controlledPanel(first).hasAttribute('inert')).toBe(true);
  expect(controlledPanel(second).hidden).toBe(true);
  first.click();
  await tick();
  expect(first.getAttribute('aria-expanded')).toBe('true');
  expect(controlledPanel(first).hidden).toBe(false);
  expect(controlledPanel(first).hasAttribute('inert')).toBe(false);
  expect(controlledPanel(second).hidden).toBe(true);
  expect(submit).not.toHaveBeenCalled();
});

test('starts open without announcing a change and reports actual trigger and programmatic transitions once', async (): Promise<void> => {
  const onOpenChange = vi.fn<(open: boolean) => void>();
  const disclosure = renderDisclosure(document.body, 'Initially open', { initiallyOpen: true, onOpenChange });
  await tick();
  const trigger = findTrigger('Initially open');
  const panel = controlledPanel(trigger);

  expect(trigger.getAttribute('aria-expanded')).toBe('true');
  expect(panel.hidden).toBe(false);
  disclosure.open();
  expect(onOpenChange).not.toHaveBeenCalled();

  trigger.click();
  disclosure.close();
  await tick();
  expect(trigger.getAttribute('aria-expanded')).toBe('false');
  expect(panel.hidden).toBe(true);
  expect(onOpenChange.mock.calls).toEqual([[false]]);

  disclosure.open();
  disclosure.open();
  await tick();
  expect(trigger.getAttribute('aria-expanded')).toBe('true');
  expect(panel.hidden).toBe(false);
  expect(onOpenChange.mock.calls).toEqual([[false], [true]]);

  const done = panel.querySelector('button');
  if (!done) throw new Error('Missing panel close button');
  done.click();
  await tick();
  expect(panel.hidden).toBe(true);
  expect(onOpenChange.mock.calls).toEqual([[false], [true], [false]]);
});

test('a controlled disclosure requests changes and follows the parent without emitting again', async (): Promise<void> => {
  const parent = new SvelteMap([['expanded', false]]);
  const onOpenChange = vi.fn<(open: boolean) => void>();
  renderDisclosure(document.body, 'Controlled editor', {
    get expanded(): boolean | undefined { return parent.get('expanded'); },
    onOpenChange
  });
  await tick();
  const trigger = findTrigger('Controlled editor');
  const panel = controlledPanel(trigger);
  const draft = panel.querySelector('input');
  if (!draft) throw new Error('Missing draft input');

  trigger.click();
  await tick();
  expect(onOpenChange.mock.calls).toEqual([[true]]);
  expect(trigger.getAttribute('aria-expanded')).toBe('false');
  expect(panel.hidden).toBe(true);

  parent.set('expanded', true);
  await tick();
  expect(trigger.getAttribute('aria-expanded')).toBe('true');
  expect(panel.hidden).toBe(false);

  draft.focus();
  parent.set('expanded', false);
  await tick();
  expect(trigger.getAttribute('aria-expanded')).toBe('false');
  expect(panel.hidden).toBe(true);
  expect(panel.hasAttribute('inert')).toBe(true);
  expect(document.activeElement).toBe(trigger);
  expect(onOpenChange.mock.calls).toEqual([[true]]);
});

test('programmatic close restores focus only if the panel has focus, and open never moves focus', async (): Promise<void> => {
  const disclosure = renderDisclosure(document.body, 'Programmatic editor');
  const outside = document.createElement('button');
  document.body.append(outside);
  await tick();
  const trigger = findTrigger('Programmatic editor');
  const panel = controlledPanel(trigger);
  const draft = panel.querySelector('input');
  if (!draft) throw new Error('Missing draft input');

  outside.focus();
  disclosure.open();
  await tick();
  expect(document.activeElement).toBe(outside);
  disclosure.close();
  await tick();
  expect(document.activeElement).toBe(outside);

  disclosure.open();
  await tick();
  draft.focus();
  disclosure.close();
  await tick();
  expect(document.activeElement).toBe(trigger);
  expect(panel.hidden).toBe(true);
});

test('opening from a parent effect does not make a later close reopen the panel', async (): Promise<void> => {
  const disclosure = renderDisclosure(document.body, 'Parent-driven editor');
  const stop = openFromParentEffect(disclosure.open);
  try {
    await tick();
    const trigger = findTrigger('Parent-driven editor');
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    trigger.click();
    await tick();
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
  } finally {
    stop();
  }
});

test('reports transitions in order when restoring focus reopens the panel', async (): Promise<void> => {
  const onOpenChange = vi.fn<(open: boolean) => void>();
  const disclosure = renderDisclosure(document.body, 'Reopening editor', { initiallyOpen: true, onOpenChange });
  await tick();
  const trigger = findTrigger('Reopening editor');
  const panel = controlledPanel(trigger);
  const draft = panel.querySelector('input');
  if (!draft) throw new Error('Missing draft input');
  draft.focus();
  trigger.addEventListener('focus', disclosure.open, { once: true });

  disclosure.close();
  await tick();

  expect(onOpenChange.mock.calls).toEqual([[false], [true]]);
  expect(trigger.getAttribute('aria-expanded')).toBe('true');
  expect(panel.hidden).toBe(false);
});

test('keeps the same draft and restores focus when content closes its panel', async (): Promise<void> => {
  renderDisclosure(document.body, 'Editor');
  await tick();
  const trigger = findTrigger('Editor');
  const panel = controlledPanel(trigger);
  const draft = panel.querySelector('input');
  const done = panel.querySelector('button');
  if (!draft || !done) throw new Error('Missing panel controls');

  trigger.click();
  await tick();
  draft.value = 'Edited';
  done.focus();
  done.click();
  await tick();
  expect(document.activeElement).toBe(trigger);
  expect(trigger.getAttribute('aria-expanded')).toBe('false');
  expect(panel.hidden).toBe(true);

  trigger.click();
  await tick();
  expect(controlledPanel(trigger)).toBe(panel);
  expect(panel.querySelector('input')).toBe(draft);
  expect(draft.value).toBe('Edited');

  const outside = document.createElement('button');
  document.body.append(outside);
  outside.focus();
  done.click();
  await tick();
  expect(panel.hidden).toBe(true);
  expect(document.activeElement).toBe(outside);
});
