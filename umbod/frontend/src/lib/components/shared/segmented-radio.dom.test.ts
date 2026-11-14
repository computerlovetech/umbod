import { afterEach, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';
import SegmentedRadio from './SegmentedRadio.svelte';

const components: ReturnType<typeof mount>[] = [];
const options = [
  { value: 'compact', label: 'Compact' },
  { value: 'comfortable', label: 'Comfortable' },
  { value: 'spacious', label: 'Spacious' }
] as const;

afterEach(async (): Promise<void> => {
  await Promise.all(components.map((component) => unmount(component)));
  components.length = 0;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function group(name: string): HTMLFieldSetElement {
  const fieldset = document.querySelector<HTMLFieldSetElement>(`fieldset[aria-label="${name}"]`);
  if (!fieldset) throw new Error(`Radio group not found: ${name}`);
  return fieldset;
}

function radios(name: string): HTMLInputElement[] {
  return [...group(name).querySelectorAll<HTMLInputElement>('input[type="radio"]')];
}

function radio(name: string, value: string): HTMLInputElement {
  const input = radios(name).find((entry) => entry.value === value);
  if (!input) throw new Error(`Radio not found: ${name}, ${value}`);
  return input;
}

test('renders a visible legend, labelled native radios and the controlled checked value', async (): Promise<void> => {
  components.push(mount(SegmentedRadio, {
    target: document.body,
    props: { label: 'Density', options, value: 'comfortable', onchange: vi.fn() }
  }));
  await tick();
  expect(group('Density').querySelector('legend')?.textContent).toBe('Density');
  expect(group('Density').dataset.size).toBe('normal');
  expect(radios('Density').map((input) => input.labels?.[0]?.textContent?.trim())).toEqual(['Compact', 'Comfortable', 'Spacious']);
  expect(radios('Density').map((input) => [input.value, input.checked])).toEqual([
    ['compact', false], ['comfortable', true], ['spacious', false]
  ]);
  expect(radios('Density').every((input) => !input.disabled)).toBe(true);
});

test('publishes the selected value and gives each instance an independent native radio group', async (): Promise<void> => {
  const onchange = vi.fn<(value: string) => void>();
  for (const accessibleName of ['Primary density', 'Secondary density']) {
    components.push(mount(SegmentedRadio, {
      target: document.body,
      props: { label: 'Density', accessibleName, options, value: 'compact', onchange }
    }));
  }
  await tick();
  const primaryNames = radios('Primary density').map((input) => input.name);
  expect(primaryNames[0]).not.toBe('');
  expect(new Set(primaryNames).size).toBe(1);
  expect(new Set(radios('Secondary density').map((input) => input.name)).size).toBe(1);
  expect(radio('Secondary density', 'compact').name).not.toBe(primaryNames[0]);
  radio('Primary density', 'spacious').click();
  await tick();
  expect(onchange).toHaveBeenCalledExactlyOnceWith('spacious');
  expect(radio('Primary density', 'compact').checked).toBe(false);
  expect(radio('Primary density', 'spacious').checked).toBe(true);
  expect(radio('Secondary density', 'compact').checked).toBe(true);
});

test('disables the fieldset and every radio without publishing clicks', async (): Promise<void> => {
  const onchange = vi.fn<(value: string) => void>();
  components.push(mount(SegmentedRadio, {
    target: document.body,
    props: { label: 'Density', options, value: 'compact', disabled: true, onchange }
  }));
  await tick();
  expect(group('Density').disabled).toBe(true);
  expect(radios('Density').every((input) => input.disabled)).toBe(true);
  radio('Density', 'spacious').click();
  await tick();
  expect(onchange).not.toHaveBeenCalled();
  expect(radio('Density', 'compact').checked).toBe(true);
});

test('reacts to parent-controlled value, label, size and disabled prop changes without emitting changes', async (): Promise<void> => {
  const props = new SvelteMap<string, string>([['value', 'compact'], ['label', 'Density']]);
  const onchange = vi.fn<(value: string) => void>();
  components.push(mount(SegmentedRadio, {
    target: document.body,
    props: {
      get label(): string { return props.get('label')!; },
      get value(): string { return props.get('value')!; },
      get disabled(): boolean { return props.get('disabled') === 'true'; },
      get size(): 'normal' | 'compact' { return props.get('size') === 'compact' ? 'compact' : 'normal'; },
      options,
      onchange
    }
  }));
  await tick();
  expect(radio('Density', 'compact').checked).toBe(true);
  props.set('value', 'spacious');
  props.set('label', 'Layout density');
  props.set('disabled', 'true');
  props.set('size', 'compact');
  await tick();
  expect(group('Layout density').querySelector('legend')?.textContent).toBe('Layout density');
  expect(radio('Layout density', 'compact').checked).toBe(false);
  expect(radio('Layout density', 'spacious').checked).toBe(true);
  expect(group('Layout density').disabled).toBe(true);
  expect(group('Layout density').dataset.size).toBe('compact');
  expect(radios('Layout density').every((input) => input.disabled)).toBe(true);
  props.set('value', 'comfortable');
  props.set('disabled', 'false');
  props.set('size', 'normal');
  await tick();
  expect(radio('Layout density', 'spacious').checked).toBe(false);
  expect(radio('Layout density', 'comfortable').checked).toBe(true);
  expect(group('Layout density').disabled).toBe(false);
  expect(group('Layout density').dataset.size).toBe('normal');
  expect(radios('Layout density').every((input) => !input.disabled)).toBe(true);
  expect(onchange).not.toHaveBeenCalled();
});
