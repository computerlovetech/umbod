import { Window } from 'happy-dom';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { captureInvalidSubmission } from './form-validation';
import { modalDialog } from './modal-dialog';
import { PersonalServersState } from './personal-servers-state.svelte';
import { InMemoryPersonalServers } from '$lib/admin/personal-mcp-servers/in-memory';

let document: Document;
let window: Window;
beforeEach(() => {
  window = new Window();
  document = window.document as unknown as Document;
  vi.stubGlobal('HTMLElement', window.HTMLElement);
});
afterEach(() => { vi.unstubAllGlobals(); });

function formFixture(): { form: HTMLFormElement; invalid: HTMLInputElement; secret: HTMLInputElement } {
  const form = document.createElement('form');
  const invalid = document.createElement('input');
  invalid.required = true;
  const secret = document.createElement('input');
  secret.type = 'password';
  secret.name = 'clientSecret';
  secret.value = 'secret-sentinel';
  form.append(invalid, secret);
  document.body.append(form);
  return { form, invalid, secret };
}
function dialogFixture(): { dialog: HTMLDialogElement; opener: HTMLButtonElement; heading: HTMLHeadingElement; fallback: HTMLHeadingElement } {
  const opener = document.createElement('button');
  const fallback = document.createElement('h1');
  fallback.id = 'personal-servers-heading';
  fallback.tabIndex = -1;
  const dialog = document.createElement('dialog');
  const heading = document.createElement('h2');
  heading.tabIndex = -1;
  heading.dataset.dialogTitle = '';
  dialog.append(heading);
  dialog.showModal = vi.fn(() => { dialog.setAttribute('open', ''); });
  dialog.close = vi.fn(() => { dialog.removeAttribute('open'); });
  document.body.append(opener, fallback, dialog);
  opener.focus();
  return { dialog, opener, heading, fallback };
}

describe('personal form native invalid capture', () => {
  test.each(['registration', 'policy'])('clears state and DOM secret before submit on invalid %s fields without cancelling native feedback', (formKind) => {
    const state = new PersonalServersState(new InMemoryPersonalServers());
    if (formKind === 'registration') state.openCreate();
    state.form.setKind('preconfigured_confidential');
    state.form.set('secret', 'secret-sentinel');
    const { form, invalid, secret } = formFixture();
    const submit = vi.fn();
    form.addEventListener('submit', submit);
    const cleanup = captureInvalidSubmission(state.handleNativeInvalid)(form);
    const event = new window.Event('invalid', { bubbles: false, cancelable: true }) as unknown as Event;
    invalid.dispatchEvent(event);
    expect(state.form.secret).toBe('');
    expect(secret.value).toBe('');
    expect(state.message).toBe('Complete all required fields before continuing. The client secret was cleared; enter a fresh secret before submitting again.');
    expect(state.message).not.toContain('secret-sentinel');
    expect(event.defaultPrevented).toBe(false);
    expect(submit).not.toHaveBeenCalled();
    if (typeof cleanup === 'function') cleanup();
    state.form.set('secret', 'fresh');
    secret.value = 'fresh';
    invalid.dispatchEvent(new window.Event('invalid', { bubbles: false }) as unknown as Event);
    expect(state.form.secret).toBe('fresh');
    expect(secret.value).toBe('fresh');
  });
});

describe('personal modal native dialog lifecycle', () => {
  test('opens modally, focuses its non-destructive title and restores its opener after teardown', async () => {
    const { dialog, opener, heading } = dialogFixture();
    const cleanup = modalDialog(vi.fn(), 'personal-servers-heading')(dialog);
    expect(dialog.showModal).toHaveBeenCalledTimes(1);
    expect(document.activeElement).toBe(heading);
    if (typeof cleanup === 'function') cleanup();
    await Promise.resolve();
    expect(dialog.close).toHaveBeenCalledTimes(1);
    expect(document.activeElement).toBe(opener);
  });
  test('cancel delegates to guarded state close and prevents the browser bypassing that guard', () => {
    const { dialog } = dialogFixture();
    const close = vi.fn();
    const cleanup = modalDialog(close, 'personal-servers-heading')(dialog);
    const cancel = new window.Event('cancel', { cancelable: true }) as unknown as Event;
    dialog.dispatchEvent(cancel);
    expect(cancel.defaultPrevented).toBe(true);
    expect(close).toHaveBeenCalledTimes(1);
    expect(dialog.open).toBe(true);
    expect(dialog.close).not.toHaveBeenCalled();
    if (typeof cleanup === 'function') cleanup();
    dialog.dispatchEvent(new window.Event('cancel', { cancelable: true }) as unknown as Event);
    expect(close).toHaveBeenCalledTimes(1);
  });
  test.each(['removed', 'disabled', 'inert'])('restores the fallback heading if the opener becomes %s', async (reason) => {
    const { dialog, opener, fallback } = dialogFixture();
    const cleanup = modalDialog(vi.fn(), 'personal-servers-heading')(dialog);
    if (reason === 'removed') opener.remove();
    if (reason === 'disabled') opener.disabled = true;
    if (reason === 'inert') opener.setAttribute('inert', '');
    if (typeof cleanup === 'function') cleanup();
    await Promise.resolve();
    expect(document.activeElement).toBe(fallback);
  });
});
