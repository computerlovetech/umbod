import { afterEach, expect, test, vi } from 'vitest';
import { createRawSnippet, mount, tick, unmount } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';
import Checkbox from './Checkbox.svelte';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

function checkbox(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[type="checkbox"]');
  if (!input) throw new Error('Checkbox not found');
  return input;
}

function label(): HTMLLabelElement {
  const element = checkbox().labels?.[0];
  if (!element) throw new Error('Checkbox label not found');
  return element;
}

test('clicking the full label toggles the native checkbox and forwards change events', async (): Promise<void> => {
  const onchange = vi.fn((event: Event): boolean => (event.currentTarget as HTMLInputElement).checked);
  component = mount(Checkbox, { target: document.body, props: {
    id: 'scope-read', label: 'Read files', checked: false, onchange
  } });
  await tick();
  expect(label().textContent?.trim()).toBe('Read files');
  expect(label().htmlFor).toBe('scope-read');
  label().click();
  await tick();
  expect(checkbox().checked).toBe(true);
  expect(onchange).toHaveBeenCalledTimes(1);
  expect(onchange).toHaveLastReturnedWith(true);
  label().click();
  await tick();
  expect(checkbox().checked).toBe(false);
  expect(onchange).toHaveBeenCalledTimes(2);
  expect(onchange).toHaveLastReturnedWith(false);
});

test('follows parent-owned checked updates without emitting change events', async (): Promise<void> => {
  const values = new SvelteMap<string, boolean>([['checked', false]]);
  const onchange = vi.fn<(event: Event) => void>();
  component = mount(Checkbox, { target: document.body, props: {
    id: 'scope-write', label: 'Write files',
    get checked(): boolean { return values.get('checked') === true; }, onchange
  } });
  await tick();
  expect(checkbox().checked).toBe(false);
  values.set('checked', true);
  await tick();
  expect(checkbox().checked).toBe(true);
  values.set('checked', false);
  await tick();
  expect(checkbox().checked).toBe(false);
  expect(onchange).not.toHaveBeenCalled();
});

test('disabled checkboxes ignore input and label clicks', async (): Promise<void> => {
  const onchange = vi.fn<(event: Event) => void>();
  component = mount(Checkbox, { target: document.body, props: {
    id: 'scope-disabled', label: 'Unavailable scope', checked: false, disabled: true, onchange
  } });
  await tick();
  expect(checkbox().disabled).toBe(true);
  label().click();
  checkbox().click();
  await tick();
  expect(checkbox().checked).toBe(false);
  expect(onchange).not.toHaveBeenCalled();
});

test('forwards native form and accessibility attributes and remains focusable', async (): Promise<void> => {
  component = mount(Checkbox, { target: document.body, props: {
    id: 'consent', label: 'Allow access', checked: false,
    name: 'scope', value: 'files:read', required: true,
    'aria-describedby': 'consent-description', 'aria-invalid': true,
    'aria-label': 'Allow file access', class: 'consent-input'
  } });
  await tick();
  const input = checkbox();
  expect(input.id).toBe('consent');
  expect(input.name).toBe('scope');
  expect(input.value).toBe('files:read');
  expect(input.required).toBe(true);
  expect(input.validity.valueMissing).toBe(true);
  expect(input.getAttribute('aria-describedby')).toBe('consent-description');
  expect(input.getAttribute('aria-invalid')).toBe('true');
  expect(input.getAttribute('aria-label')).toBe('Allow file access');
  expect(input.classList.contains('consent-input')).toBe(true);
  expect(input.tabIndex).toBe(0);
  input.focus();
  expect(document.activeElement).toBe(input);
});

test('renders rich label content inside the clickable label', async (): Promise<void> => {
  const onchange = vi.fn((event: Event): boolean => (event.currentTarget as HTMLInputElement).checked);
  const labelContent = createRawSnippet((): { render: () => string } => ({
    render: (): string => '<strong>https://issuer.example</strong>'
  }));
  component = mount(Checkbox, { target: document.body, props: {
    id: 'issuer', label: 'Issuer', labelContent, checked: false, onchange
  } });
  await tick();
  const content = label().querySelector('strong');
  expect(content).not.toBeNull();
  expect(content!.textContent).toBe('https://issuer.example');
  content!.click();
  await tick();
  expect(onchange).toHaveReturnedWith(true);
});
