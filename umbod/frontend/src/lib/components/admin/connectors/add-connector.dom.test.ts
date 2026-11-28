import { goto } from '$app/navigation';
import { mount, tick, unmount } from 'svelte';
import { afterEach, expect, test, vi } from 'vitest';
import { submittedConnector } from '#lib/admin/portable-connectors/fixtures.test-support.js';
import { portableRow } from '#lib/admin/unified-connectors.js';
import AddConnector from './AddConnector.svelte';
import { AddConnectorState } from './add-connector-state.svelte.js';

const navigation = vi.hoisted(() => ({ state: {} as App.PageState, url: new URL('https://umbod.test/admin/downstream-mcp-connectors') }));
const toastError = vi.hoisted(() => vi.fn<(message: string) => void>());
vi.mock('$app/state', async () => {
  const { fromStore, writable } = await import('svelte/store');
  const historyState = writable<App.PageState>({});
  const reactiveHistory = fromStore(historyState);
  Object.defineProperty(navigation, 'state', { get: () => reactiveHistory.current, set: (state: App.PageState): void => historyState.set(state) });
  return { page: navigation };
});
vi.mock('$app/navigation', () => ({
  goto: vi.fn<typeof goto>(),
  replaceState: (url: URL, state: App.PageState): void => { navigation.url = url; navigation.state = state; }
}));
vi.mock('#lib/components/feedback/index.js', () => ({ useToast: (): { error: typeof toastError } => ({ error: toastError }) }));

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  navigation.state = {};
  navigation.url = new URL('https://umbod.test/admin/downstream-mcp-connectors');
  vi.resetAllMocks();
});

function button(label: string): HTMLButtonElement {
  const control = Array.from(document.querySelectorAll('button')).find((element) => (element.getAttribute('aria-label') ?? element.textContent.trim()).startsWith(label));
  if (!control) throw new Error(`Button not found: ${label}`);
  return control;
}

function pickerDialog(): HTMLDialogElement | null {
  return document.querySelector<HTMLDialogElement>('dialog[open]');
}

async function startHandoff(): Promise<AddConnectorState> {
  const state = new AddConnectorState();
  state.registerSetup({ kind: 'mcp', nativeAvailable: () => false, nativeUnavailable: () => false, disabled: () => false, create: vi.fn() });
  component = mount(AddConnector, { target: document.body, props: { state } });
  await tick();
  button('Add connector').click();
  await tick();
  button('OpenAPI specification').click();
  await tick();
  expect(goto).not.toHaveBeenCalled();
  return state;
}

test('keeps the same open picker while loading and hands off when the destination registers', async (): Promise<void> => {
  const load = Promise.withResolvers<void>();
  vi.mocked(goto).mockReturnValue(load.promise);
  const state = await startHandoff();
  const picker = pickerDialog();
  expect(picker).not.toBeNull();
  button('Next').click();
  await tick();

  expect(goto).toHaveBeenCalledTimes(1);
  expect(pickerDialog()).toBe(picker);
  expect(button('Next').getAttribute('aria-disabled')).toBe('true');
  expect(button('Close').disabled).toBe(true);
  button('Next').click();
  expect(goto).toHaveBeenCalledTimes(1);

  const create = vi.fn((_trigger: HTMLButtonElement): void => { expect(pickerDialog()).toBe(picker); });
  navigation.state = { openConnectorSetup: 'openapi' };
  state.registerSetup({ kind: 'openapi', nativeAvailable: () => false, nativeUnavailable: () => false, disabled: () => false, create });
  await vi.waitFor(() => expect(create).toHaveBeenCalledExactlyOnceWith(button('Add connector')));
  load.resolve();
  await load.promise;
  await tick();
  expect(pickerDialog()).toBeNull();
  expect(toastError).not.toHaveBeenCalled();
});

test('keeps the selected type and re-enables Next when navigation fails', async (): Promise<void> => {
  const load = Promise.withResolvers<void>();
  vi.mocked(goto).mockReturnValue(load.promise);
  await startHandoff();
  const picker = pickerDialog();
  expect(picker).not.toBeNull();
  const next = button('Next');
  next.focus();
  next.click();
  await tick();
  load.reject(new Error('Unavailable'));
  await expect(load.promise).rejects.toThrow('Unavailable');
  await vi.waitFor(() => expect(next.hasAttribute('aria-disabled')).toBe(false));
  expect(document.activeElement).toBe(next);

  expect(pickerDialog()).toBe(picker);
  expect(button('OpenAPI specification').getAttribute('aria-pressed')).toBe('true');
  expect(button('Close').disabled).toBe(false);
  expect(toastError).toHaveBeenCalledTimes(1);
});

async function choosePortable(rows: readonly ReturnType<typeof portableRow>[]): Promise<void> {
  const state = new AddConnectorState();
  state.registerSetup({ kind: 'mcp', nativeAvailable: () => false, nativeUnavailable: () => false, disabled: () => false, create: vi.fn() });
  component = mount(AddConnector, { target: document.body, props: { state, unifiedRows: rows } });
  await tick();
  button('Add connector').click();
  await tick();
  const portable = button('Portable connector');
  expect(portable.textContent).toContain('Configure a portable connector that’s already been submitted.');
  expect(portable.disabled).toBe(false);
  portable.click();
  await tick();
  button('Next').click();
  await tick();
  expect(goto).not.toHaveBeenCalled();
  expect(pickerDialog()?.textContent).toContain('Choose a submitted portable connector');
}

test('opens the existing configuration route from the portable submission picker', async (): Promise<void> => {
  await choosePortable([portableRow(submittedConnector)]);
  expect(pickerDialog()?.textContent).not.toMatch(/Source|Publish|Activate|Check & save|Credentials/i);
  const submission = document.querySelector<HTMLButtonElement>('[aria-label="Submitted portable connectors"] button');
  if (!submission) throw new Error('Missing submitted connector');
  expect(submission.textContent).toContain(submittedConnector.name);
  const navigationComplete = Promise.withResolvers<void>();
  vi.mocked(goto).mockReturnValue(navigationComplete.promise);
  submission.click();
  await tick();
  expect(goto).toHaveBeenCalledExactlyOnceWith(`/admin/portable-connectors?connector=${submittedConnector.connector_id}`, { reset: false });
  expect(submission.disabled).toBe(true);
  navigationComplete.resolve();
  await vi.waitFor(() => expect(pickerDialog()).toBeNull());
});

test('offers no create action when no portable connectors have been submitted', async (): Promise<void> => {
  await choosePortable([]);
  expect(pickerDialog()?.textContent).toContain('No portable connectors have been submitted yet.');
  expect(pickerDialog()?.querySelectorAll('button')).toHaveLength(2);
  button('Back').click();
  await tick();
  expect(button('Portable connector').getAttribute('aria-pressed')).toBe('true');
  expect(goto).not.toHaveBeenCalled();
});
