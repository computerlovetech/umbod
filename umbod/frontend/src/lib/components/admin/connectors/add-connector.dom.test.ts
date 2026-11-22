import { goto } from '$app/navigation';
import { mount, tick, unmount } from 'svelte';
import { afterEach, expect, test, vi } from 'vitest';
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
