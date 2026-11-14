import { afterEach, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';
import TextAreaField from './TextAreaField.svelte';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

test('renders a labelled multiline field with native validation and accessibility attributes', async (): Promise<void> => {
  component = mount(TextAreaField, { target: document.body, props: {
    id: 'criteria', name: 'criteria', label: 'Criteria', value: 'First line\nSecond line',
    required: true, maxlength: 4000, rows: 4, 'aria-describedby': 'criteria-error',
    'aria-invalid': true
  } });
  await tick();
  const input = document.querySelector('textarea');
  expect(input).not.toBeNull();
  expect(document.querySelector('label')!.htmlFor).toBe(input!.id);
  expect(input!.value).toBe('First line\nSecond line');
  expect(input!.name).toBe('criteria');
  expect(input!.required).toBe(true);
  expect(input!.maxLength).toBe(4000);
  expect(input!.getAttribute('rows')).toBe('4');
  expect(input!.getAttribute('aria-describedby')).toBe('criteria-error');
  expect(input!.getAttribute('aria-invalid')).toBe('true');
});

test('forwards edits while values and disabled state remain caller-owned', async (): Promise<void> => {
  const values = new SvelteMap<string, string | boolean>([['value', 'Initial'], ['disabled', false]]);
  const oninput = vi.fn((event: Event): string => (event.currentTarget as HTMLTextAreaElement).value);
  component = mount(TextAreaField, { target: document.body, props: {
    id: 'criteria', label: 'Criteria', get value(): string { return String(values.get('value')); },
    get disabled(): boolean { return values.get('disabled') === true; }, oninput
  } });
  await tick();
  const input = document.querySelector('textarea');
  expect(input).not.toBeNull();
  input!.value = 'Draft';
  input!.dispatchEvent(new Event('input', { bubbles: true }));
  expect(oninput).toHaveReturnedWith('Draft');
  expect(values.get('value')).toBe('Initial');
  values.set('value', 'Authoritative');
  values.set('disabled', true);
  await tick();
  expect(input!.value).toBe('Authoritative');
  expect(input!.disabled).toBe(true);
});
