import { afterEach, expect, it, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { InMemoryPersonalAccessTokens } from '#lib/personal-access-tokens/in-memory-api.test-support.js';
import type { ClipboardWriter } from '#lib/admin/clipboard.js';
import PersonalTokens from './PersonalTokens.svelte';
import { HttpError } from '#lib/admin/infrastructure/transport.js';

const cleanups: Array<() => Promise<void>> = [];

afterEach(async (): Promise<void> => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
});

function render(api: InMemoryPersonalAccessTokens = new InMemoryPersonalAccessTokens(), clipboard: ClipboardWriter = { writeText: async (): Promise<void> => {} }): HTMLDivElement {
  const target = document.createElement('div');
  document.body.append(target);
  const component = mount(PersonalTokens, { target, props: { apiFactory: () => api, clipboardFactory: () => clipboard } });
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

function labelledControl<T extends HTMLElement>(target: ParentNode, name: string): T {
  const label = [...target.querySelectorAll('label')].find((candidate): boolean => candidate.textContent?.trim() === name);
  if (!label) throw new Error(`Missing label: ${name}`);
  return element<T>(target, `[id="${label.htmlFor}"]`);
}

function agentLogsCheckbox(target: ParentNode): HTMLInputElement {
  const checkbox = labelledControl<HTMLInputElement>(target, 'Send agent logs');
  expect(checkbox.type).toBe('checkbox');
  return checkbox;
}

async function openCreate(target: ParentNode): Promise<HTMLDialogElement> {
  await vi.waitFor(() => expect(button(target, 'Create access token').disabled).toBe(false));
  button(target, 'Create access token').click();
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

it('opens the form on demand, selects options and updates the list after issuance and revocation', async (): Promise<void> => {
  const api = new InMemoryPersonalAccessTokens();
  const copied: string[] = [];
  const target = render(api, { writeText: async (value: string): Promise<void> => { copied.push(value); } });
  await vi.waitFor(() => expect(target.textContent).toContain('No personal access tokens.'));
  expect(target.querySelector('form, dialog, details')).toBeNull();
  expect(target.textContent).not.toContain('Refresh');
  expect(button(target, 'Create access token').querySelector('svg[aria-hidden="true"]')).not.toBeNull();
  const dialog = await openCreate(target);
  expect(dialog.open).toBe(true);
  expect(button(dialog, 'Create token').querySelector('svg')).toBeNull();
  expect(element<HTMLInputElement>(dialog, 'input').required).toBe(true);
  expect(element<HTMLInputElement>(dialog, 'input').maxLength).toBe(256);
  const permission = agentLogsCheckbox(dialog);
  expect(permission.checked).toBe(false);
  const expiration = labelledControl<HTMLButtonElement>(dialog, 'Expiration');
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
  await vi.waitFor(() => expect(element<HTMLElement>(dialog, '[role="alert"]').textContent).toBe('Select at least one permission.'));
  expect(api.createCalls).toBe(0);
  permission.click();
  expect(permission.checked).toBe(true);
  button(dialog, 'Create token').click();
  await vi.waitFor(() => expect(element<HTMLTextAreaElement>(dialog, 'textarea').value).toBe('test-only-secret'));
  expect(dialog.querySelector('form, input')).toBeNull();
  expect(document.activeElement).toBe(element<HTMLTextAreaElement>(dialog, 'textarea'));
  const list = element<HTMLUListElement>(target, 'ul[aria-label="Personal access tokens"]');
  expect(list.textContent).toContain('Agent logs');
  expect(list.textContent).toContain('active');
  expect(element<HTMLTimeElement>(list, 'time').dateTime).toBe(api.rows[0].expires_at);
  expect(api.listCalls).toBe(1);
  expect(copied).toEqual([]);
  button(dialog, 'Copy token').click();
  await vi.waitFor(() => expect(copied).toHaveLength(1));
  expect(copied).toEqual(['test-only-secret']);
  await vi.waitFor(() => expect(element<HTMLElement>(dialog, '[role="status"]').textContent).toBe('Token copied.'));
  button(dialog, 'Done').click();
  await tick();
  expect(target.querySelector('dialog, textarea')).toBeNull();
  const reopened = await openCreate(target);
  expect(element<HTMLInputElement>(reopened, 'input').value).toBe('');
  expect(agentLogsCheckbox(reopened).checked).toBe(false);
  expect(labelledControl<HTMLButtonElement>(reopened, 'Expiration').textContent).toContain('30 days');
  expect(reopened.querySelector('textarea')).toBeNull();
  button(reopened, 'Cancel').click();
  await tick();
  button(target, 'Delete Agent logs').click();
  await vi.waitFor(() => expect(list.textContent).toContain('No personal access tokens.'));
  expect(api.listCalls).toBe(1);
  expect(target.textContent).not.toContain('test-only-secret');
});

it('lists every token by default and matches a selected scope within a combined-scope token', async (): Promise<void> => {
  const api = new InMemoryPersonalAccessTokens();
  const first = await api.create({ name: 'Combined token', expires_at: '2099-01-01T00:00:00Z', permissions: { telemetry: 'write' } });
  const second = await api.create({ name: 'Other token', expires_at: '2099-01-01T00:00:00Z', permissions: { telemetry: 'write' } });
  api.rows = [
    { ...first.metadata, scopes: ['files:read', 'telemetry:write'] },
    { ...second.metadata, scopes: ['tools:read'] }
  ];
  const target = render(api);
  const rows = (): string[] => [...target.querySelectorAll('ul[aria-label="Personal access tokens"] > li')].map((row): string => row.textContent ?? '');
  await vi.waitFor(() => expect(rows()).toHaveLength(2));
  expect(rows()[0]).toContain('Files · read, Send agent logs');
  expect(rows()[1]).toContain('Tools · read');
  const filter = labelledControl<HTMLButtonElement>(target, 'Permission');
  expect(filter.textContent).toContain('All permissions');
  filter.click();
  await tick();
  const scopeOptions = (): HTMLElement[] => [...document.querySelectorAll<HTMLElement>('[role="listbox"][aria-label="Permission"] [role="option"]')];
  const options = scopeOptions();
  expect(options.map((option): string | undefined => option.querySelector('span')?.textContent)).toEqual(['All permissions', 'Files · read', 'Send agent logs', 'Tools · read']);
  options[2].click();
  await vi.waitFor(() => expect(filter.textContent).toContain('Send agent logs'));
  expect(rows()).toEqual([expect.stringContaining('Combined token')]);
  filter.click();
  await tick();
  expect(scopeOptions()[0]?.textContent).toContain('All permissions');
  scopeOptions()[0].click();
  await tick();
  expect(rows()).toEqual([expect.stringContaining('Combined token'), expect.stringContaining('Other token')]);
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
  agentLogsCheckbox(dialog).click();
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
  const target = render(new InMemoryPersonalAccessTokens(), { writeText: (): Promise<void> => new Promise<void>((resolve): void => { finishCopy = resolve; }) });
  const dialog = await openCreate(target);
  fillName(dialog, 'Copy token');
  agentLogsCheckbox(dialog).click();
  button(dialog, 'Create token').click();
  await vi.waitFor(() => expect(dialog.querySelector('textarea')).not.toBeNull());
  button(dialog, 'Copy token').click();
  await tick();
  expect(button(dialog, 'Done').disabled).toBe(false);
  button(dialog, 'Done').click();
  await tick();
  finishCopy();
  await tick();
  const reopened = await openCreate(target);
  expect(reopened.querySelector('textarea')).toBeNull();
  expect(target.textContent).not.toContain('Token copied.');
});

it('removes secret output on unmount and never renders a late issued secret', async (): Promise<void> => {
  const api = new InMemoryPersonalAccessTokens();
  const target = render(api);
  const dialog = await openCreate(target);
  fillName(dialog, 'First token');
  agentLogsCheckbox(dialog).click();
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
  agentLogsCheckbox(pendingDialog).click();
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
