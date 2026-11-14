import { afterEach, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';
import TextField from './TextField.svelte';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

test('renders a labelled plain text field and forwards native input and autofill attributes', async (): Promise<void> => {
  component = mount(TextField, { target: document.body, props: {
    id: 'namespace-name', name: 'namespace_name', label: 'Name', value: 'Research',
    autocomplete: 'off', 'data-1p-ignore': 'true', 'aria-describedby': 'name-error',
    'aria-invalid': true, required: true, maxlength: 255
  } });
  await tick();
  const input = document.querySelector<HTMLInputElement>('input');
  expect(input).not.toBeNull();
  expect(document.querySelector('label')?.htmlFor).toBe(input!.id);
  expect(input!.type).toBe('text');
  expect(input!.name).toBe('namespace_name');
  expect(input!.value).toBe('Research');
  expect(input!.autocomplete).toBe('off');
  expect(input!.getAttribute('data-1p-ignore')).toBe('true');
  expect(input!.getAttribute('aria-describedby')).toBe('name-error');
  expect(input!.getAttribute('aria-invalid')).toBe('true');
  expect(input!.required).toBe(true);
  expect(input!.maxLength).toBe(255);
});

test('forwards input events and follows caller-owned value and disabled state', async (): Promise<void> => {
  const values = new SvelteMap<string, string | boolean>([['name', 'Initial'], ['disabled', false]]);
  const oninput = vi.fn((event: Event): string => (event.currentTarget as HTMLInputElement).value);
  component = mount(TextField, { target: document.body, props: {
    id: 'plain-name', label: 'Name', get value(): string { return String(values.get('name')); },
    get disabled(): boolean { return values.get('disabled') === true; }, oninput
  } });
  await tick();
  const input = document.querySelector<HTMLInputElement>('input');
  expect(input).not.toBeNull();
  input!.value = 'Draft';
  input!.dispatchEvent(new Event('input', { bubbles: true }));
  expect(oninput).toHaveReturnedWith('Draft');
  expect(values.get('name')).toBe('Initial');
  values.set('name', 'Authoritative');
  values.set('disabled', true);
  await tick();
  expect(input!.value).toBe('Authoritative');
  expect(input!.disabled).toBe(true);
});
