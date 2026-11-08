import { afterEach, expect, it, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { InMemoryPersonalAccessTokens } from '$lib/personal-access-tokens/in-memory-api.test-support';
import { InMemoryTelemetrySetup } from '$lib/telemetry-setup/in-memory-api.test-support';
import type { ClipboardWriter } from '$lib/admin/clipboard';
import TelemetrySetup from './TelemetrySetup.svelte';
import { HttpError } from '$lib/admin/infrastructure/transport';

const cleanups: Array<() => Promise<void>> = [];

afterEach(async (): Promise<void> => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
});

function render(api: InMemoryPersonalAccessTokens = new InMemoryPersonalAccessTokens(), setup: InMemoryTelemetrySetup = new InMemoryTelemetrySetup(), clipboard: ClipboardWriter = { writeText: async (): Promise<void> => {} }): HTMLDivElement {
  const target = document.createElement('div');
  document.body.append(target);
  const component = mount(TelemetrySetup, { target, props: { apiFactory: () => api, setupApiFactory: () => setup, clipboardFactory: () => clipboard } });
  cleanups.push(async (): Promise<void> => { await unmount(component); target.remove(); });
  flushSync();
  return target;
}

function button(target: ParentNode, label: string): HTMLButtonElement {
  const found = [...target.querySelectorAll('button')].find((element): boolean => (element.getAttribute('aria-label') ?? element.textContent?.trim()) === label);
  if (!found) throw new Error(`Missing button: ${label}`);
  return found;
}

function element<T extends Element>(target: ParentNode, selector: string): T {
  const found = target.querySelector<T>(selector);
  if (!found) throw new Error(`Missing element: ${selector}`);
  return found;
}

function fillName(target: ParentNode, value: string): void {
  const input = element<HTMLInputElement>(target, 'input[name="token-name"]');
  input.value = value;
  input.dispatchEvent(new Event('input', { bubbles: true }));
}

function combobox(target: ParentNode, name: string): HTMLButtonElement {
  const label = [...target.querySelectorAll('label')].find((candidate): boolean => candidate.textContent === name);
  if (!label) throw new Error(`Missing label: ${name}`);
  return element<HTMLButtonElement>(target, `[id="${label.htmlFor}"]`);
}

async function openCreate(target: ParentNode): Promise<HTMLDialogElement> {
  await vi.waitFor(() => expect(button(target, 'Create token').disabled).toBe(false));
  button(target, 'Create token').click();
  await tick();
  return element<HTMLDialogElement>(target, 'dialog');
}

it('reports denied access without creation or token actions', async (): Promise<void> => {
  const api = new InMemoryPersonalAccessTokens();
  api.failure = new HttpError(403, 'Forbidden', null);
  const target = render(api);
  await vi.waitFor(() => expect(target.textContent).toContain('Your account cannot manage personal access tokens on this instance.'));
  expect(target.querySelector('form, dialog, button')).toBeNull();
  expect(target.textContent).not.toContain('Simulated development identities');
});

it.each(['disabled', 'not_configured'] as const)('keeps the list and revocation without creation or refresh when %s', async (reason): Promise<void> => {
  const api = new InMemoryPersonalAccessTokens();
  await api.create({ name: 'Existing', expires_at: '2099-01-01T00:00:00Z', permissions: { telemetry: 'write' } });
  const setup = new InMemoryTelemetrySetup();
  setup.value = { status: 'unavailable', reason };
  const target = render(api, setup);
  await vi.waitFor(() => expect(target.textContent).toContain('Contact your operator'));
  expect(target.querySelector('form, dialog, input, details')).toBeNull();
  expect(target.textContent).not.toContain('Create token');
  expect(target.textContent).not.toContain('Refresh');
  expect(element<HTMLTimeElement>(target, 'time').dateTime).toBe('2099-01-01T00:00:00.000Z');
  button(target, 'Delete Existing').click();
  await vi.waitFor(() => expect(target.textContent).toContain('No personal access tokens.'));
  expect(api.rows).toEqual([]);
  expect(api.listCalls).toBe(1);
});

it('opens the form on demand, selects options and updates the list after issuance and revocation', async (): Promise<void> => {
  const api = new InMemoryPersonalAccessTokens();
  const copied: string[] = [];
  const target = render(api, new InMemoryTelemetrySetup(), { writeText: async (value: string): Promise<void> => { copied.push(value); } });
  await vi.waitFor(() => expect(target.textContent).toContain('No personal access tokens.'));
  expect(target.querySelector('form, dialog, details')).toBeNull();
  expect(target.textContent).not.toContain('Refresh');
  const dialog = await openCreate(target);
  expect(dialog.open).toBe(true);
  expect(element<HTMLInputElement>(dialog, 'input').required).toBe(true);
  expect(element<HTMLInputElement>(dialog, 'input').maxLength).toBe(256);
  const agent = combobox(dialog, 'Agent');
  expect(agent.textContent).toContain('Codex');
  agent.dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true, cancelable: true }));
  await tick();
  expect(element<HTMLElement>(dialog, '[role="listbox"]').getAttribute('aria-label')).toBe('Agent');
  agent.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
  await vi.waitFor(() => expect(agent.textContent).toContain('Claude Code'));
  const expiration = combobox(dialog, 'Expiration');
  expect(expiration.textContent).toContain('30 days');
  expiration.click();
  await tick();
  const options = [...dialog.querySelectorAll<HTMLElement>('[role="option"]')];
  expect(options.map((option): string | null | undefined => option.querySelector('span')?.textContent)).toEqual(['7 days', '30 days', '60 days', '90 days']);
  options[0].click();
  await vi.waitFor(() => expect(expiration.textContent).toContain('7 days'));
  expect(api.createCalls).toBe(0);
  fillName(dialog, 'Agent logs');
  button(dialog, 'Create token').click();
  await vi.waitFor(() => expect(element<HTMLTextAreaElement>(dialog, 'textarea').value).toContain('test-only-secret'));
  expect(dialog.querySelector('form, input')).toBeNull();
  expect(document.activeElement).toBe(element<HTMLTextAreaElement>(dialog, 'textarea'));
  expect(JSON.parse(element<HTMLTextAreaElement>(dialog, 'textarea').value).env.OTEL_LOGS_EXPORTER).toBe('otlp');
  const list = element<HTMLUListElement>(target, 'ul[aria-label="Personal access tokens"]');
  expect(list.textContent).toContain('Agent logs');
  expect(list.textContent).toContain('active');
  expect(element<HTMLTimeElement>(list, 'time').dateTime).toBe(api.rows[0].expires_at);
  expect(api.listCalls).toBe(1);
  expect(copied).toEqual([]);
  button(dialog, 'Copy configuration').click();
  await vi.waitFor(() => expect(copied).toHaveLength(1));
  expect(copied[0]).toContain('/v1/logs');
  button(dialog, 'Done').click();
  await tick();
  expect(target.querySelector('dialog, textarea')).toBeNull();
  const reopened = await openCreate(target);
  expect(element<HTMLInputElement>(reopened, 'input').value).toBe('');
  expect(combobox(reopened, 'Agent').textContent).toContain('Codex');
  expect(combobox(reopened, 'Expiration').textContent).toContain('30 days');
  expect(reopened.querySelector('textarea')).toBeNull();
  button(reopened, 'Cancel').click();
  await tick();
  button(target, 'Delete Agent logs').click();
  await vi.waitFor(() => expect(list.textContent).toContain('No personal access tokens.'));
  expect(api.listCalls).toBe(1);
  expect(target.textContent).not.toContain('test-only-secret');
});

it('offers an icon-only delete action for already revoked tokens without changing other rows', async (): Promise<void> => {
  const api = new InMemoryPersonalAccessTokens();
  const issued = await api.create({ name: 'Old token', expires_at: '2099-01-01T00:00:00Z', permissions: { telemetry: 'write' } });
  api.rows = [{ ...issued.metadata, status: 'revoked' }];
  await api.create({ name: 'Keep token', expires_at: '2099-01-01T00:00:00Z', permissions: { telemetry: 'write' } });
  const target = render(api);
  await vi.waitFor(() => expect(target.textContent).toContain('revoked'));
  const action = button(target, 'Delete Old token');
  expect(action.textContent?.trim()).toBe('');
  expect(action.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
  expect(action.parentElement?.lastElementChild).toBe(action);
  action.click();
  await vi.waitFor(() => expect(target.textContent).not.toContain('Old token'));
  expect(target.textContent).toContain('Keep token');
  expect(api.rows.map((row): string => row.name)).toEqual(['Keep token']);
});

it('blocks duplicate submission and dismissal while issuing', async (): Promise<void> => {
  const api = new InMemoryPersonalAccessTokens();
  let finish: () => void = (): void => {};
  api.beforeCreate = (): Promise<void> => new Promise<void>((resolve): void => { finish = resolve; });
  const target = render(api);
  const dialog = await openCreate(target);
  fillName(dialog, 'Pending token');
  button(dialog, 'Create token').click();
  await tick();
  expect(element<HTMLFieldSetElement>(dialog, 'fieldset').disabled).toBe(true);
  expect(button(dialog, 'Cancel').disabled).toBe(true);
  button(dialog, 'Cancel').click();
  element<HTMLFormElement>(dialog, 'form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  dialog.dispatchEvent(new Event('cancel', { cancelable: true }));
  await tick();
  expect(dialog.open).toBe(true);
  expect(api.createCalls).toBe(1);
  finish();
  await vi.waitFor(() => expect(dialog.querySelector('textarea')).not.toBeNull());
  dialog.dispatchEvent(new Event('cancel', { cancelable: true }));
  await tick();
  expect(target.querySelector('dialog, textarea')).toBeNull();
  const reopened = await openCreate(target);
  expect(element<HTMLInputElement>(reopened, 'input').value).toBe('');
  expect(reopened.querySelector('textarea')).toBeNull();
});

it('allows dismissal while copying and fences the late result', async (): Promise<void> => {
  let finishCopy: () => void = (): void => {};
  const target = render(new InMemoryPersonalAccessTokens(), new InMemoryTelemetrySetup(), { writeText: (): Promise<void> => new Promise<void>((resolve): void => { finishCopy = resolve; }) });
  const dialog = await openCreate(target);
  fillName(dialog, 'Copy token');
  button(dialog, 'Create token').click();
  await vi.waitFor(() => expect(dialog.querySelector('textarea')).not.toBeNull());
  button(dialog, 'Copy configuration').click();
  await tick();
  expect(button(dialog, 'Done').disabled).toBe(false);
  button(dialog, 'Done').click();
  await tick();
  finishCopy();
  await tick();
  const reopened = await openCreate(target);
  expect(reopened.querySelector('textarea')).toBeNull();
  expect(target.textContent).not.toContain('Configuration copied.');
});

it('removes secret output on unmount and never renders a late issued secret', async (): Promise<void> => {
  const api = new InMemoryPersonalAccessTokens();
  const target = render(api);
  const dialog = await openCreate(target);
  fillName(dialog, 'First token');
  button(dialog, 'Create token').click();
  await vi.waitFor(() => expect(target.querySelector('textarea')).not.toBeNull());
  const cleanup = cleanups.pop();
  if (!cleanup) throw new Error('Missing cleanup');
  await cleanup();
  expect(target.querySelector('textarea, dialog')).toBeNull();
  let finish: () => void = (): void => {};
  api.beforeCreate = (): Promise<void> => new Promise<void>((resolve): void => { finish = resolve; });
  const next = render(api);
  const pendingDialog = await openCreate(next);
  fillName(pendingDialog, 'Late token');
  button(pendingDialog, 'Create token').click();
  await tick();
  const dispose = cleanups.pop();
  if (!dispose) throw new Error('Missing cleanup');
  await dispose();
  finish();
  await tick();
  expect(next.querySelector('textarea, dialog')).toBeNull();
  expect(next.textContent).not.toContain('test-only-secret');
});

it('shows a sanitized load error with no refresh control', async (): Promise<void> => {
  const api = new InMemoryPersonalAccessTokens();
  api.failure = new Error('secret backend details');
  const target = render(api);
  await vi.waitFor(() => expect(target.querySelector('[role="alert"]')?.textContent).toContain('Could not load personal access tokens.'));
  expect(target.textContent).not.toContain('secret backend details');
  expect(target.textContent).not.toContain('Refresh');
  expect(target.querySelector('dialog, button')).toBeNull();
});
