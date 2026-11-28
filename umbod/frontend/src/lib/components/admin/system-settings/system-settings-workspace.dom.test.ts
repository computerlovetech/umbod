import { createRawSnippet, mount, tick, unmount } from 'svelte';
import { afterEach, expect, test, vi } from 'vitest';
import type { FilesystemSettings } from '#lib/admin/system-settings/domain/filesystem-settings.js';
import type { FilesystemSettingsAdministration } from '#lib/admin/system-settings/filesystem-settings-port.js';
import { AuthenticationRequiredError } from '#lib/admin/infrastructure/transport.js';
import { deferred } from '#lib/files/fixtures.test-support.js';
import SystemSettingsWorkspace from './SystemSettingsWorkspace.svelte';
import { FilesystemSettingsState } from './filesystem-settings-state.svelte';

type ApprovalSource = FilesystemSettings['require_mcp_file_deletion_approval']['source'];

let component: ReturnType<typeof mount> | undefined;
let state: FilesystemSettingsState | undefined;

afterEach(async (): Promise<void> => {
  state?.dispose();
  if (component) await unmount(component);
  state = undefined;
  component = undefined;
  document.body.replaceChildren();
});

function settings(value: boolean, source: ApprovalSource): FilesystemSettings {
  return { require_mcp_file_deletion_approval: { value, source } };
}

function mountWith(api: FilesystemSettingsAdministration): Promise<void> {
  state = new FilesystemSettingsState(api);
  const diagnostics = createRawSnippet(() => ({ render: (): string => '<h2>Agent diagnostics</h2>' }));
  const providerMappings = createRawSnippet(() => ({ render: (): string => '<p>Provider mappings editor</p>' }));
  component = mount(SystemSettingsWorkspace, { target: document.body, props: { state, section: 'filesystem', diagnosticsAllowed: true, diagnostics, providerMappings } });
  return state.load();
}

function button(label: string): HTMLButtonElement {
  const match = [...document.querySelectorAll('button')].find((candidate) => candidate.textContent?.trim() === label);
  if (!match) throw new Error(`Missing button: ${label}`);
  return match;
}

function toggle(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[type="checkbox"][aria-label="Require approval for MCP file deletion"]');
  if (!input) throw new Error('Missing approval toggle');
  return input;
}

test('lists all settings sections and displays only Filesystem by default', async (): Promise<void> => {
  await mountWith({ get: async () => settings(true, 'built_in_default'), update: async () => settings(false, 'admin_override') });
  await tick();

  const sidebar = document.querySelector('aside[aria-label="Settings sections"]');
  expect(sidebar?.querySelectorAll('li')).toHaveLength(3);
  expect(sidebar?.querySelector('a[aria-current="page"]')?.textContent).toMatch(/Filesystem\s*1 setting/);
  expect(sidebar?.querySelector('a[href="/admin/system-settings?section=agent-diagnostics"]')?.textContent).toMatch(/Agent diagnostics\s*2 settings/);
  expect(sidebar?.querySelector('a[href="/admin/system-settings?section=provider-group-mappings"]')?.textContent).toMatch(/Group mappings\s*1 setting/);
  expect(document.querySelector('section[aria-label="Agent diagnostics settings"]')).toBeNull();
  expect(document.body.textContent).not.toContain('Provider mappings editor');
  expect(document.querySelector('input[type="search"], [role="searchbox"]')).toBeNull();
  expect(document.body.textContent).not.toMatch(/Retention|Integrations/);
  const descriptionId = toggle().getAttribute('aria-describedby') ?? '';
  expect(document.getElementById(descriptionId)?.textContent).toContain('doesn’t grant delete permission or change the browser’s confirmation dialog');
  expect(button('Save changes').disabled).toBe(true);
});

test('does not offer provider mappings when the shared settings guard denies access', async (): Promise<void> => {
  await mountWith({
    get: async (): Promise<FilesystemSettings> => { throw new AuthenticationRequiredError(); },
    update: async () => settings(false, 'admin_override')
  });
  await tick();

  expect(document.querySelector('a[href="/admin/system-settings?section=provider-group-mappings"]')).toBeNull();
  expect(document.querySelector('a[href="/admin/system-settings?section=agent-diagnostics"]')).not.toBeNull();
});

test('discards a toggle draft and sends an explicit false value only when saved', async (): Promise<void> => {
  const update = vi.fn<FilesystemSettingsAdministration['update']>().mockResolvedValue(settings(false, 'admin_override'));
  await mountWith({ get: async () => settings(true, 'built_in_default'), update });
  await tick();

  toggle().click();
  await tick();
  expect(document.body.textContent).toContain('new MCP file deletion requests won’t ask for confirmation');
  expect(update).not.toHaveBeenCalled();
  button('Discard changes').click();
  await tick();
  expect(toggle().checked).toBe(true);
  expect(button('Save changes').disabled).toBe(true);

  toggle().click();
  await tick();
  button('Save changes').click();
  await vi.waitFor(() => expect(document.body.textContent).toContain('Admin override'));
  expect(update).toHaveBeenCalledExactlyOnceWith(
    { require_mcp_file_deletion_approval: { operation: 'set', value: false } },
    expect.any(AbortSignal)
  );
  expect(toggle().checked).toBe(false);
  expect(button('Save changes').disabled).toBe(true);
});

test('stages reset for a saved override and adopts the server default even when it is off', async (): Promise<void> => {
  const update = vi.fn<FilesystemSettingsAdministration['update']>().mockResolvedValue(settings(false, 'deployment_default'));
  await mountWith({ get: async () => settings(true, 'admin_override'), update });
  await tick();

  button('Reset to default').click();
  await tick();
  expect(toggle().checked).toBe(true);
  expect(document.body.textContent).toContain('The current value is shown until then');
  expect(update).not.toHaveBeenCalled();
  button('Save changes').click();
  await vi.waitFor(() => expect(document.body.textContent).toContain('Deployment default'));

  expect(update).toHaveBeenCalledExactlyOnceWith(
    { require_mcp_file_deletion_approval: { operation: 'reset' } },
    expect.any(AbortSignal)
  );
  expect(toggle().checked).toBe(false);
  expect(document.body.textContent).not.toContain('Reset to default');
});

test('shows loading and offers a retry after a failed read', async (): Promise<void> => {
  const pending = deferred<FilesystemSettings>();
  const get = vi.fn<FilesystemSettingsAdministration['get']>()
    .mockReturnValueOnce(pending.promise)
    .mockResolvedValueOnce(settings(true, 'built_in_default'));
  const load = mountWith({ get, update: async () => settings(false, 'admin_override') });
  await tick();
  expect(document.querySelector('[role="status"]')?.textContent).toContain('Loading filesystem settings');

  pending.reject(new Error('Read failed'));
  await load;
  await tick();
  expect(document.querySelector('[role="alert"]')?.textContent).toBe('Could not load filesystem settings.');
  expect(document.querySelector('input[type="checkbox"]')).toBeNull();
  button('Try again').click();
  await vi.waitFor(() => expect(toggle().checked).toBe(true));
  expect(document.querySelector('[role="alert"]')).toBeNull();
});

test('prevents duplicate saves in flight and preserves an unconfirmed draft for retry', async (): Promise<void> => {
  const pending = deferred<FilesystemSettings>();
  const update = vi.fn<FilesystemSettingsAdministration['update']>().mockReturnValue(pending.promise);
  await mountWith({ get: async () => settings(true, 'built_in_default'), update });
  await tick();
  toggle().click();
  await tick();
  button('Save changes').click();
  await tick();
  expect(button('Save changes').disabled).toBe(true);
  expect(button('Discard changes').disabled).toBe(true);
  expect(toggle().disabled).toBe(true);
  button('Save changes').click();
  expect(update).toHaveBeenCalledTimes(1);

  pending.reject(new Error('Write failed'));
  await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toContain('Could not confirm'));
  expect(document.querySelector('[role="status"]')?.textContent).toBe('Unsaved changes');
  expect(document.body.textContent).toContain('Built-in default');
  expect(button('Save changes').disabled).toBe(false);
  expect(toggle().checked).toBe(false);
});
