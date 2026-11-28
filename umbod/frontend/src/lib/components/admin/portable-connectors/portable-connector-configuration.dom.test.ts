import { mount, tick, unmount } from 'svelte';
import { afterEach, expect, test, vi } from 'vitest';
import { submittedConnector, unconfiguredConnector } from '#lib/admin/portable-connectors/fixtures.test-support.js';
import type { PortableConnectorConfiguration as Configuration } from '#lib/admin/portable-connectors/domain/schemas.js';
import type { PortableConnectors } from '#lib/admin/portable-connectors/port.js';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import { portableRow } from '#lib/admin/unified-connectors.js';
import PortableConnectorConfiguration from './PortableConnectorConfiguration.svelte';
import { PortableConfigurationState } from './portable-configuration-state.svelte.js';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

function show(api: Pick<PortableConnectors, 'getConfiguration' | 'replaceConfiguration'>): void {
  component = mount(PortableConnectorConfiguration, {
    target: document.body,
    props: { state: new PortableConfigurationState(portableRow(submittedConnector), api) }
  });
}

function control<ElementType extends Element>(selector: string): ElementType {
  const element = document.querySelector<ElementType>(selector);
  if (!element) throw new Error(`Missing control: ${selector}`);
  return element;
}

function submit(): void {
  control('form').dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));
}

test('validates the submitted fields, saves only configuration and reloads the saved values', async (): Promise<void> => {
  let persisted = unconfiguredConnector;
  const pending = Promise.withResolvers<Configuration>();
  const getConfiguration = vi.fn<PortableConnectors['getConfiguration']>(async () => persisted);
  const replaceConfiguration = vi.fn<PortableConnectors['replaceConfiguration']>(async (_id, { configuration }) => {
    await pending.promise;
    persisted = { ...unconfiguredConnector, connector: { ...submittedConnector, configured: true }, configuration };
    return persisted;
  });
  const api = { getConfiguration, replaceConfiguration };
  show(api);
  await vi.waitFor(() => expect(document.querySelector('form')).not.toBeNull());
  expect(document.body.textContent).toContain('Not configured');
  expect(document.body.textContent).toContain('Inactive');
  expect(document.body.textContent).toContain('Enter non-secret values only.');
  expect(document.body.textContent).not.toMatch(/Credentials|Publish|Activate|Configuration check/i);
  submit();
  await tick();
  expect(replaceConfiguration).not.toHaveBeenCalled();
  expect(document.body.textContent).toContain('Mode is required.');

  const workspace = control<HTMLInputElement>('input[type="text"]');
  workspace.value = 'Test workspace';
  workspace.dispatchEvent(new Event('input', { bubbles: true }));
  control<HTMLButtonElement>('[role="combobox"]').click();
  await tick();
  const preview = Array.from(document.querySelectorAll<HTMLLIElement>('[role="option"]')).find((option) => option.textContent.trim() === 'preview');
  if (!preview) throw new Error('Missing Mode value');
  preview.click();
  await tick();

  submit();
  submit();
  await tick();
  expect(control<HTMLButtonElement>('button[type="submit"]').disabled).toBe(true);
  expect(replaceConfiguration).toHaveBeenCalledExactlyOnceWith(
    submittedConnector.connector_id, { configuration: { workspace: 'Test workspace', mode: 'preview' } }, expect.any(AbortSignal)
  );
  pending.resolve(unconfiguredConnector);
  await vi.waitFor(() => expect(document.body.textContent).toContain('Configuration saved.'));
  expect(document.body.textContent).not.toContain('Not configured');
  expect(document.body.textContent).toContain('Configured');
  expect(document.body.textContent).toContain('Inactive');

  if (!component) throw new Error('Configuration form is not mounted');
  await unmount(component);
  show(api);
  await vi.waitFor(() => expect(control<HTMLInputElement>('input[type="text"]').value).toBe('Test workspace'));
  expect(control('[role="combobox"]').textContent).toContain('preview');
  expect(getConfiguration).toHaveBeenCalledTimes(2);
});

test('shows a distinct load failure with a retry and keeps the draft after a save failure', async (): Promise<void> => {
  const getConfiguration = vi.fn<PortableConnectors['getConfiguration']>()
    .mockRejectedValueOnce(new Error('Unavailable'))
    .mockResolvedValue({ ...unconfiguredConnector, configuration: { workspace: 'Stored', mode: 'review' } });
  const replaceConfiguration = vi.fn<PortableConnectors['replaceConfiguration']>().mockRejectedValue(new HttpError(422, 'Rejected', {}));
  show({ getConfiguration, replaceConfiguration });
  expect(document.body.textContent).toContain('Loading configuration…');
  await vi.waitFor(() => expect(document.body.textContent).toContain('Could not load'));
  const retry = Array.from(document.querySelectorAll('button')).find((button) => button.textContent.trim() === 'Reload configuration');
  if (!retry) throw new Error('Missing reload control');
  retry.click();
  await vi.waitFor(() => expect(control<HTMLInputElement>('input[type="text"]').value).toBe('Stored'));
  const workspace = control<HTMLInputElement>('input[type="text"]');
  workspace.value = 'Unsaved';
  workspace.dispatchEvent(new Event('input', { bubbles: true }));
  submit();
  await vi.waitFor(() => expect(document.body.textContent).toContain('Could not save'));
  expect(workspace.value).toBe('Unsaved');
});

test('requires a reload before retrying a write whose result was not confirmed', async (): Promise<void> => {
  const stored = { ...unconfiguredConnector, configuration: { workspace: 'Stored', mode: 'review' } };
  const getConfiguration = vi.fn<PortableConnectors['getConfiguration']>()
    .mockResolvedValueOnce(stored)
    .mockResolvedValue({ ...stored, configuration: { ...stored.configuration, workspace: 'Committed' } });
  const replaceConfiguration = vi.fn<PortableConnectors['replaceConfiguration']>()
    .mockRejectedValue(new HttpError(503, 'Unavailable', { detail: { code: 'configuration_write_unconfirmed' } }));
  show({ getConfiguration, replaceConfiguration });
  await vi.waitFor(() => expect(control<HTMLInputElement>('input[type="text"]').value).toBe('Stored'));
  submit();
  await vi.waitFor(() => expect(document.body.textContent).toContain('Could not confirm the save.'));
  expect(control<HTMLButtonElement>('button[type="submit"]').disabled).toBe(true);
  submit();
  expect(replaceConfiguration).toHaveBeenCalledTimes(1);
  const reload = Array.from(document.querySelectorAll('button')).find((button) => button.textContent.trim() === 'Reload configuration');
  if (!reload) throw new Error('Missing reload control');
  reload.click();
  await vi.waitFor(() => expect(control<HTMLInputElement>('input[type="text"]').value).toBe('Committed'));
  expect(control<HTMLButtonElement>('button[type="submit"]').disabled).toBe(false);
});
