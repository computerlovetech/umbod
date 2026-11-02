import { afterEach, expect, test, vi } from 'vitest';
import { mount, tick, unmount, type ComponentProps } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';
import { createAttachmentKey } from 'svelte/attachments';
import Button from './Button.svelte';
import ButtonLink from './ButtonLink.svelte';
import LoadingButton from './LoadingButton.svelte';
import Harness from './button.test-support.svelte';

type ButtonProps = Omit<ComponentProps<typeof Button>, 'children'>;
type LinkProps = Omit<ComponentProps<typeof ButtonLink>, 'children'>;
type LoadingProps = ComponentProps<typeof LoadingButton>;

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

async function setup(kind: 'button' | 'loading' | 'link' = 'button', initial: ButtonProps & Partial<LoadingProps> & LinkProps = {}): Promise<{
  update: (props: ButtonProps & Partial<LoadingProps> & LinkProps) => Promise<void>;
  ref: () => HTMLButtonElement | null | undefined;
}> {
  const props = new SvelteMap([['current', initial]]);
  let reference: HTMLButtonElement | null | undefined;
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(Harness, {
    target,
    props: {
      kind,
      buttonProps: (): ButtonProps => props.get('current')!,
      loadingProps: (): LoadingProps => ({ label: 'Save', loading: false, ...props.get('current') }),
      linkProps: (): LinkProps => props.get('current')!,
      getRef: (): HTMLButtonElement | undefined => reference ?? undefined,
      setRef: (element: HTMLButtonElement | null | undefined): void => { reference = element; }
    }
  });
  await tick();
  return {
    update: async (next: ButtonProps & Partial<LoadingProps> & LinkProps): Promise<void> => {
      props.set('current', next);
      await tick();
    },
    ref: (): HTMLButtonElement | null | undefined => reference
  };
}

function button(): HTMLButtonElement {
  const element = document.querySelector('button');
  if (!element) throw new Error('Expected mounted button');
  return element;
}

async function dispose(): Promise<void> {
  await unmount(component!);
  component = undefined;
}

test('forwards native identity, ARIA, data and form attributes onto the button', async (): Promise<void> => {
  const form = document.createElement('form');
  form.id = 'action-form';
  document.body.append(form);
  await setup('button', {
    id: 'save-action', 'aria-label': 'Save changes', 'aria-describedby': 'save-help',
    'aria-expanded': true, 'data-purpose': 'save', form: form.id, name: 'intent', value: 'save',
    formaction: '/save', formmethod: 'post', formnovalidate: true, title: 'Save draft'
  });
  expect(button().id).toBe('save-action');
  expect(button().getAttribute('aria-label')).toBe('Save changes');
  expect(button().getAttribute('aria-describedby')).toBe('save-help');
  expect(button().getAttribute('aria-expanded')).toBe('true');
  expect(button().dataset.purpose).toBe('save');
  expect(button().form).toBe(form);
  expect(button().name).toBe('intent');
  expect(button().value).toBe('save');
  expect(button().getAttribute('formaction')).toBe('/save');
  expect(button().getAttribute('formmethod')).toBe('post');
  expect(button().formNoValidate).toBe(true);
  expect(button().title).toBe('Save draft');
});

test('defaults to a non-submitting button and preserves native submit and reset actions', async (): Promise<void> => {
  const form = document.createElement('form');
  form.id = 'native-form';
  const input = document.createElement('input');
  input.defaultValue = 'Original';
  form.append(input);
  document.body.append(form);
  const submitted = vi.fn((event: Event): void => { event.preventDefault(); });
  const reset = vi.fn();
  form.addEventListener('submit', submitted);
  form.addEventListener('reset', reset);
  const view = await setup('button', { form: form.id });
  expect(button().type).toBe('button');
  button().click();
  expect(submitted).not.toHaveBeenCalled();
  await view.update({ form: form.id, type: 'submit' });
  button().click();
  expect(submitted).toHaveBeenCalledOnce();
  expect((submitted.mock.calls[0][0] as SubmitEvent).submitter).toBe(button());
  input.value = 'Edited';
  await view.update({ form: form.id, type: 'reset' });
  button().click();
  expect(reset).toHaveBeenCalledOnce();
  expect(input.value).toBe('Original');
});

test('forwards keyboard and nested click callbacks with the native currentTarget', async (): Promise<void> => {
  const received: Array<{ key: string; target: EventTarget | null }> = [];
  const clicked: Array<EventTarget | null> = [];
  await setup('button', {
    onkeydown: (event): void => { received.push({ key: event.key, target: event.currentTarget }); event.preventDefault(); },
    onclick: (event): void => { clicked.push(event.currentTarget); }
  });
  button().focus();
  expect(document.activeElement).toBe(button());
  const event = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
  button().dispatchEvent(event);
  expect(received).toEqual([{ key: 'Enter', target: button() }]);
  expect(event.defaultPrevented).toBe(true);
  button().querySelector('span')!.click();
  expect(clicked).toEqual([button()]);
});

test.each(['primary', 'secondary', 'danger', 'quiet'] as const)('merges %s classes and updates size, icon mode and native props without remounting', async (variant): Promise<void> => {
  const view = await setup('button', { variant, size: 'compact', iconOnly: true, class: 'consumer-action', disabled: true });
  const element = button();
  expect([...element.classList]).toEqual(expect.arrayContaining([
    'admin-shared-button', `admin-shared-button--${variant}`, 'admin-shared-button--compact', 'admin-shared-button--icon', 'consumer-action'
  ]));
  expect(element.disabled).toBe(true);
  await view.update({ variant: 'secondary', size: 'normal', iconOnly: false, class: 'replacement', id: 'updated', 'aria-pressed': true });
  expect(button()).toBe(element);
  expect(element.disabled).toBe(false);
  expect(element.id).toBe('updated');
  expect(element.getAttribute('aria-pressed')).toBe('true');
  expect([...element.classList]).toEqual(expect.arrayContaining(['admin-shared-button--secondary', 'admin-shared-button--normal', 'replacement']));
  expect(element.classList.contains('admin-shared-button--compact')).toBe(false);
  expect(element.classList.contains('admin-shared-button--icon')).toBe(false);
  expect(element.classList.contains('consumer-action')).toBe(false);
});

test.each(['button', 'loading'] as const)('%s exposes its native bound ref and cleans up spread attachments on unmount', async (kind): Promise<void> => {
  const cleaned = vi.fn();
  const attached = vi.fn((element: HTMLElement): (() => void) => {
    expect(element).toBeInstanceOf(HTMLButtonElement);
    element.dataset.attached = 'true';
    return cleaned;
  });
  const view = await setup(kind, { [createAttachmentKey()]: attached });
  const element = button();
  expect(view.ref()).toBe(element);
  expect(attached).toHaveBeenCalledWith(element);
  expect(element.dataset.attached).toBe('true');
  expect(cleaned).not.toHaveBeenCalled();
  await dispose();
  expect(view.ref()).toBeNull();
  expect(cleaned).toHaveBeenCalledOnce();
  expect(element.isConnected).toBe(false);
});

test('LoadingButton forwards native props, classes and events while pending overrides disabled and busy', async (): Promise<void> => {
  const clicked = vi.fn();
  const view = await setup('loading', {
    id: 'save', form: 'editor', name: 'intent', value: 'save', type: 'submit',
    'aria-describedby': 'hint', 'data-action': 'save', class: 'custom-loading', variant: 'quiet', size: 'compact', iconOnly: true,
    onclick: clicked, loading: true, disabled: false, 'aria-busy': false
  });
  const element = button();
  expect(element.id).toBe('save');
  expect(element.getAttribute('form')).toBe('editor');
  expect(element.name).toBe('intent');
  expect(element.value).toBe('save');
  expect(element.type).toBe('submit');
  expect(element.getAttribute('aria-describedby')).toBe('hint');
  expect(element.dataset.action).toBe('save');
  expect([...element.classList]).toEqual(expect.arrayContaining(['loading-button', 'custom-loading', 'admin-shared-button--quiet', 'admin-shared-button--compact', 'admin-shared-button--icon']));
  expect(element.disabled).toBe(true);
  expect(element.getAttribute('aria-busy')).toBe('true');
  element.click();
  expect(clicked).not.toHaveBeenCalled();
  await view.update({ loading: false, disabled: true, onclick: clicked });
  expect(element.disabled).toBe(true);
  expect(element.getAttribute('aria-busy')).toBe('false');
  await view.update({ loading: false, disabled: false, onclick: clicked });
  element.click();
  expect(clicked).toHaveBeenCalledOnce();
});

test('LoadingButton disables immediately, delays feedback and restores the label when loading ends', async (): Promise<void> => {
  vi.useFakeTimers();
  const view = await setup('loading', { label: 'Publish', loadingLabel: 'Publishing', loading: true, delayMs: 100 });
  expect(button().disabled).toBe(true);
  expect(button().getAttribute('aria-busy')).toBe('true');
  expect(button().getAttribute('aria-label')).toBe('Publish');
  expect(button().querySelector('[role="status"]')).toBeNull();
  await vi.advanceTimersByTimeAsync(99);
  await tick();
  expect(button().getAttribute('aria-label')).toBe('Publish');
  await vi.advanceTimersByTimeAsync(1);
  await tick();
  expect(button().getAttribute('aria-label')).toBe('Publishing');
  expect(button().querySelector('[role="status"]')?.textContent).toContain('Publishing');
  expect(button().querySelector('.loading-button__content')?.getAttribute('aria-hidden')).toBe('true');
  await view.update({ label: 'Published', loading: false });
  expect(button().disabled).toBe(false);
  expect(button().getAttribute('aria-busy')).toBe('false');
  expect(button().getAttribute('aria-label')).toBe('Published');
  expect(button().querySelector('[role="status"]')).toBeNull();
});

test('LoadingButton cancels obsolete feedback on completion and clears pending timers on unmount', async (): Promise<void> => {
  vi.useFakeTimers();
  const view = await setup('loading', { loading: true, delayMs: 100 });
  await vi.advanceTimersByTimeAsync(50);
  await view.update({ loading: false });
  await vi.advanceTimersByTimeAsync(100);
  await tick();
  expect(button().getAttribute('aria-label')).toBe('Save');
  expect(button().querySelector('[role="status"]')).toBeNull();
  await view.update({ loading: true, delayMs: 100 });
  expect(vi.getTimerCount()).toBe(1);
  await dispose();
  expect(vi.getTimerCount()).toBe(0);
  await vi.advanceTimersByTimeAsync(100);
  expect(document.querySelector('button')).toBeNull();
});

test.each(['primary', 'secondary', 'danger', 'quiet'] as const)('ButtonLink stays an anchor with native navigation attributes and %s button classes', async (variant): Promise<void> => {
  const clicked: Array<EventTarget | null> = [];
  const view = await setup('link', {
    href: '/destination', target: '_blank', rel: 'noopener noreferrer', id: 'destination',
    'aria-label': 'Open destination', 'data-action': 'navigate', variant, size: 'compact', class: 'consumer-link',
    onclick: (event): void => { event.preventDefault(); clicked.push(event.currentTarget); }
  });
  const anchor = document.querySelector('a')!;
  expect(document.querySelector('button')).toBeNull();
  expect(anchor.getAttribute('role')).toBeNull();
  expect(anchor.getAttribute('href')).toBe('/destination');
  expect(anchor.target).toBe('_blank');
  expect(anchor.rel).toBe('noopener noreferrer');
  expect(anchor.id).toBe('destination');
  expect(anchor.getAttribute('aria-label')).toBe('Open destination');
  expect(anchor.dataset.action).toBe('navigate');
  expect([...anchor.classList]).toEqual(expect.arrayContaining(['admin-shared-button', `admin-shared-button--${variant}`, 'admin-shared-button--compact', 'consumer-link']));
  anchor.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  expect(clicked).toEqual([anchor]);
  await view.update({ href: '/updated', variant: 'secondary', size: 'normal', class: 'updated-link' });
  expect(document.querySelector('a')).toBe(anchor);
  expect(anchor.getAttribute('href')).toBe('/updated');
  expect(anchor.hasAttribute('target')).toBe(false);
  expect(anchor.hasAttribute('rel')).toBe(false);
  expect([...anchor.classList]).toEqual(expect.arrayContaining(['admin-shared-button--secondary', 'admin-shared-button--normal', 'updated-link']));
  expect(anchor.classList.contains('consumer-link')).toBe(false);
  expect(anchor.classList.contains('admin-shared-button--compact')).toBe(false);
});
