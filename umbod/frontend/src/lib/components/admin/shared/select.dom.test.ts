import { afterEach, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import SelectTestHarness from './SelectTestHarness.test-support.svelte';
import { SelectTestModel } from './select.test-support.svelte';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

async function setup(searchable: boolean = true): Promise<SelectTestModel> {
  const model = new SelectTestModel();
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(SelectTestHarness, { target, props: { model, searchable } });
  await tick();
  return model;
}

function trigger(): HTMLInputElement | HTMLButtonElement {
  return document.querySelector('[role="combobox"]')!;
}

async function key(key: string): Promise<KeyboardEvent> {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
  trigger().dispatchEvent(event);
  await tick();
  return event;
}

async function input(value: string): Promise<void> {
  (trigger() as HTMLInputElement).value = value;
  trigger().dispatchEvent(new Event('input', { bubbles: true }));
  await tick();
}

function options(): HTMLElement[] {
  return Array.from(document.querySelectorAll('[role="option"]'));
}

test('search opens filtered current options, empty status and new results without native selects', async (): Promise<void> => {
  const model = await setup();
  expect(document.querySelector('select')).toBeNull();
  trigger().focus();
  await tick();
  expect(document.querySelector('dialog > [role="listbox"]')).not.toBeNull();
  await input('empty');
  expect(options()).toHaveLength(0);
  expect(document.querySelector('[role="status"]')?.textContent).toBe('Nothing matches');
  await input('team');
  expect(options().map((option) => option.textContent)).toEqual(['Result team']);
  const pointer = new PointerEvent('pointerdown', { bubbles: true, cancelable: true });
  options()[0].dispatchEvent(pointer);
  expect(pointer.defaultPrevented).toBe(true);
  options()[0].click();
  await tick();
  expect(model.selections).toEqual(['filtered value']);
  expect((trigger() as HTMLInputElement).value).toBe('');
  expect(document.activeElement).toBe(trigger());
  expect(trigger().getAttribute('aria-expanded')).toBe('false');
});

test('button mode opens at the first choice, uses encoded IDs, skips disabled choices and follows controlled updates', async (): Promise<void> => {
  const model = await setup(false);
  await key('ArrowDown');
  expect(trigger().getAttribute('aria-activedescendant')).toBe('test-choice-option-%20first%20value%20');
  await key('ArrowDown');
  expect(trigger().getAttribute('aria-activedescendant')).toBe('test-choice-option-second');
  model.replace([{ value: 'replacement', label: 'Replacement' }], 'replacement');
  await tick();
  expect(trigger().textContent).toContain('Replacement');
  expect(trigger().getAttribute('aria-activedescendant')).toBe('test-choice-option-replacement');
  const enter = await key('Enter');
  expect(enter.defaultPrevented).toBe(true);
  expect(model.selections).toEqual(['replacement']);
  expect(document.querySelector('input[name="choice"]')?.getAttribute('value')).toBe('replacement');
});

test('search editing keys remain native, arrows select and Enter never submits', async (): Promise<void> => {
  const model = await setup();
  expect((await key(' ')).defaultPrevented).toBe(false);
  expect((await key('Home')).defaultPrevented).toBe(false);
  expect((await key('End')).defaultPrevented).toBe(false);
  await key('ArrowDown');
  expect(trigger().getAttribute('aria-activedescendant')).toBe('test-choice-option-%20first%20value%20');
  expect((await key('Enter')).defaultPrevented).toBe(true);
  expect(model.selections).toEqual([' first value ']);
});

test('Escape consumes only the popup dismissal and Tab, blur and outside dismiss', async (): Promise<void> => {
  await setup();
  const bubbled = vi.fn();
  document.querySelector('dialog')!.addEventListener('keydown', bubbled);
  await key('ArrowDown');
  bubbled.mockClear();
  expect((await key('Escape')).defaultPrevented).toBe(true);
  expect(bubbled).not.toHaveBeenCalled();
  expect(document.querySelector('dialog form')).not.toBeNull();
  expect((await key('Escape')).defaultPrevented).toBe(false);
  expect(bubbled).toHaveBeenCalledOnce();
  await key('ArrowDown');
  expect((await key('Tab')).defaultPrevented).toBe(false);
  expect(document.querySelector('[role="listbox"]')).toBeNull();
  trigger().click();
  await tick();
  document.querySelector('form > button')!.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  await tick();
  expect(document.querySelector('[role="listbox"]')).toBeNull();
  trigger().focus();
  await tick();
  trigger().blur();
  await tick();
  expect(document.querySelector('[role="listbox"]')).toBeNull();
});

test.each([false, true])('portalled options cannot select after disabled changes, inherited=%s', async (inherited: boolean): Promise<void> => {
  const model = await setup();
  await key('ArrowDown');
  const stale = options()[0];
  model.disable(inherited);
  if (inherited) await tick();
  stale.click();
  await key('Enter');
  flushSync();
  expect(model.selections).toEqual([]);
  if (!inherited) {
    expect(trigger().getAttribute('aria-expanded')).toBe('false');
    expect(document.querySelector('[role="listbox"]')).toBeNull();
  }
});

test('remeasures above-trigger geometry when filtered popup height changes', async (): Promise<void> => {
  vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(720);
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ left: 100, right: 300, top: 650, bottom: 694, width: 200, height: 44, x: 100, y: 650, toJSON: (): object => ({}) });
  vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockImplementation(function (this: HTMLElement): number {
    return this.querySelectorAll('[role="option"]').length * 36;
  });
  const model = await setup();
  await key('ArrowDown');
  await vi.waitFor(() => expect((document.querySelector('[role="listbox"]') as HTMLElement).style.top).toBe('538px'));
  await input('narrow');
  await vi.waitFor(() => expect((document.querySelector('[role="listbox"]') as HTMLElement).style.top).toBe('610px'));
  model.replace([{ value: 'one', label: 'One' }, { value: 'two', label: 'Two' }, { value: 'three', label: 'Three' }], '');
  await tick();
  await vi.waitFor(() => expect((document.querySelector('[role="listbox"]') as HTMLElement).style.top).toBe('538px'));
  expect((document.querySelector('[role="listbox"]') as HTMLElement).style.maxHeight).toBe('108px');
});

test('removed or newly disabled choices cannot be selected by stale popup events', async (): Promise<void> => {
  const model = await setup();
  await key('ArrowDown');
  const stale = options()[0];
  model.replace([{ value: ' first value ', label: 'No longer enabled', disabled: true }], '');
  stale.click();
  await key('Enter');
  expect(model.selections).toEqual([]);
});
