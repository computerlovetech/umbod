import { afterEach, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { goto, refreshAll } from '$app/navigation';
import type { BrowserSubmitFunction, BrowserSubmitUpdate } from '#lib/admin/operations/browser-submit.js';
import { ConnectorDetailsBrowserRoute, type ConnectorDetailBundle } from '#lib/admin/connector-details-browser-api.js';
import { OpenApiConnectorDetailsBrowserRoute } from '#lib/admin/openapi-connector-details-browser-api.js';
import { OpenApiConnectorToolsBrowserRoute } from '#lib/admin/openapi-connector-tools-browser-api.js';
import type { ConnectorListItem } from '#lib/admin/connectors.js';
import type { OpenApiConnectorListItem } from '#lib/admin/openapi-connectors.js';
import { DownstreamMcpConnectorsRoute } from '#lib/admin/downstream-mcp-connectors-api.js';
import { HttpInstanceConfigurationRoute } from '#lib/admin/instance-configuration-api.js';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import { serverFixture } from '#lib/admin/personal-mcp-servers/fixtures.test-support.js';
import { AddConnectorState } from './add-connector-state.svelte.js';
import DownstreamMcpPageContent from '../downstream-mcp-connectors/DownstreamMcpPageContent.svelte';
import ConnectorList from './ConnectorList.svelte';
import OpenApiConnectorList from '../openapi-connectors/OpenApiConnectorList.svelte';

const navigation = vi.hoisted(() => ({ path: '/admin/connectors', capability: 'tools' }));
const submission = vi.hoisted(() => ({ update: vi.fn<BrowserSubmitUpdate>().mockResolvedValue(undefined) }));
vi.mock('$app/state', () => ({ navigating: { to: null, from: null }, page: {
  state: {},
  get url(): URL { return new URL(`${navigation.path}?connector=a&capability=${navigation.capability}`, 'https://umbod.test'); },
  get shallow(): { url: URL } { return { url: new URL(`${navigation.path}?connector=b&capability=${navigation.capability}`, 'https://umbod.test') }; }
} }));
vi.mock('$app/navigation', () => ({ goto: vi.fn(), refreshAll: vi.fn(), replaceState: vi.fn() }));
vi.mock('#lib/components/feedback/index.js', () => ({ useToast: (): object => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }) }));
vi.mock('#lib/admin/operations/browser-submit.js', () => ({
  browserSubmit: (form: HTMLFormElement, callback?: BrowserSubmitFunction): { destroy: () => void } => {
    const submit = async (event: Event): Promise<void> => {
      event.preventDefault();
      const cleanups: Array<() => void> = [];
      const after = await callback?.({ formData: new FormData(form), formElement: form, submitter: null, cancel: (): void => {}, onComplete: (cleanup): void => { cleanups.push(cleanup); } });
      try {
        await after?.({ result: { type: 'success', status: 200, data: { status: 'saved', connectorId: 'b' } }, update: submission.update });
      } finally {
        cleanups.forEach((cleanup): void => cleanup());
      }
    };
    const listener = (event: Event): void => { void submit(event); };
    form.addEventListener('submit', listener);
    return { destroy: (): void => form.removeEventListener('submit', listener) };
  }
}));

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  navigation.path = '/admin/connectors';
  navigation.capability = 'tools';
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

function connector(id: string): ConnectorListItem {
  return { id, name: `Connector ${id}`, description: '', sourceLabel: 'Built-in', configureHref: `/admin/connectors/${id}/configuration`, publicationStatus: 'Draft', isConfigured: true, canPublish: true, canUnpublish: false, tools: [] };
}

function bundle(id: string): ConnectorDetailBundle {
  return {
    detail: { status: 'ready', connector: { id, name: `Connector ${id}`, description: '', sourceLabel: 'Built-in', publicationStatus: 'Draft' }, tools: [{ operationName: `${id}-tool`, label: `${id}-tool`, description: '', parameters: [], outputSchema: { status: 'not-declared' }, activationStatus: 'disabled' }] },
    configurationFields: [],
    promptCatalog: { prompts: [{ name: `${id}-prompt`, description: '', arguments: [], activation_status: 'disabled' }], available_actions: ['activate'] },
    resourceCatalog: { resources: [{ kind: 'resource', name: `${id}-resource`, description: '', uri: `kb://${id}`, activationStatus: 'disabled' }], availableActions: ['activate'] }
  };
}

function renderNative(failed = false): void {
  component = mount(ConnectorList, { target: document.body, props: { connectors: [connector('a'), connector('b')], selectedConnectorId: 'a', initialDetail: bundle('a'), initialDetailFailed: failed, onconfigure: (): void => {} } });
}

test.each([false, true])('native refreshed data for A reloads shallow-selected B without seeding A detail or failure (%s)', async (failed): Promise<void> => {
  const get = vi.spyOn(ConnectorDetailsBrowserRoute.prototype, 'get').mockResolvedValue(bundle('b'));
  for (let refresh = 0; refresh < 2; refresh += 1) {
    renderNative(failed);
    await vi.waitFor(() => expect(document.querySelector('#selected-connector-heading')?.textContent).toBe('Connector b'));
    await vi.waitFor(() => expect(document.body.textContent).toContain('b-tool'));
    expect(document.body.textContent).not.toContain('a-tool');
    expect(get).toHaveBeenLastCalledWith('b', expect.any(AbortSignal));
    expect(document.querySelector<HTMLInputElement>('form.save-tools input[name="connectorId"]')?.value).toBe('b');
    await unmount(component!);
    component = undefined;
  }
  expect(get).toHaveBeenCalledTimes(2);
  expect(goto).not.toHaveBeenCalled();
});

test.each(['tools', 'prompts', 'resources'])('native %s save reconciles in place without reset or refresh', async (capability): Promise<void> => {
  navigation.capability = capability;
  const get = vi.spyOn(ConnectorDetailsBrowserRoute.prototype, 'get').mockResolvedValue(bundle('b'));
  renderNative();
  await vi.waitFor(() => expect(document.querySelector('#selected-connector-heading')?.textContent).toBe('Connector b'));
  await vi.waitFor(() => expect(document.querySelector('form.save-tools')).not.toBeNull());
  const indicators = document.querySelector('[aria-label="Connector indicators"]');
  expect(Array.from(indicators?.querySelectorAll('dt') ?? [], (term): string => term.textContent!.trim())).toEqual(['Source', 'Tools']);
  expect(document.querySelector('[aria-label="Status spotlight"]')).toBeNull();
  const form = document.querySelector<HTMLFormElement>('form.save-tools');
  expect(form).not.toBeNull();
  const toggle = document.querySelector<HTMLInputElement>('input[type="checkbox"]');
  expect(toggle).not.toBeNull();
  toggle!.click();
  await tick();
  form!.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));
  await vi.waitFor(() => expect(submission.update).toHaveBeenCalledWith({ reset: false, invalidateAll: false }));
  await tick();
  expect(document.querySelector('form.save-tools')).toBe(form);
  expect(toggle!.checked).toBe(true);
  expect(get).toHaveBeenCalledTimes(1);
  expect(refreshAll).not.toHaveBeenCalled();
  expect(goto).not.toHaveBeenCalled();
});

test('MCP refreshed data for A reloads shallow-selected B without seeding A catalogs or failure', async (): Promise<void> => {
  navigation.path = '/admin/downstream-mcp-connectors';
  navigation.capability = 'prompts';
  const first = { ...serverFixture(), connector_id: 'a', display_name: 'MCP a', authorization_mode: 'shared' as const };
  const selected = { ...first, connector_id: 'b', display_name: 'MCP b' };
  const get = vi.spyOn(DownstreamMcpConnectorsRoute.prototype, 'get').mockResolvedValue(selected);
  vi.spyOn(DownstreamMcpConnectorsRoute.prototype, 'tools').mockResolvedValue({ discovered_at: '2026-01-01T00:00:00Z', tools: [] });
  vi.spyOn(DownstreamMcpConnectorsRoute.prototype, 'prompts').mockResolvedValue(bundle('b').promptCatalog);
  vi.spyOn(DownstreamMcpConnectorsRoute.prototype, 'resources').mockResolvedValue({ resources: [], available_actions: [] });
  vi.spyOn(DownstreamMcpConnectorsRoute.prototype, 'listActivations').mockResolvedValue({ connector_id: 'b', tools: [] });
  vi.spyOn(HttpInstanceConfigurationRoute.prototype, 'get').mockRejectedValue(new HttpError(503, 'Unavailable', null));
  for (let refresh = 0; refresh < 2; refresh += 1) {
    component = mount(DownstreamMcpPageContent, { target: document.body, props: { addConnector: new AddConnectorState(), data: {
      connectors: [first, selected], selectedConnectorId: 'a', selectedDetail: first, selectedDetailFailed: true,
      catalog: { discovered_at: '2026-01-01T00:00:00Z', tools: [] }, promptCatalog: bundle('a').promptCatalog,
      resourceCatalog: bundle('a').resourceCatalog, invocationPolicies: [{ tool_id: 'a-tool', mode: 'ask', revision: 1 }]
    } } });
    await vi.waitFor(() => expect(document.querySelector('#selected-mcp-connector-heading')?.textContent).toBe('MCP b'));
    expect(document.body.textContent).toContain('b-prompt');
    expect(document.body.textContent).not.toContain('a-prompt');
    const technicalDetails = document.querySelector<HTMLDetailsElement>('details.technical-details')!;
    expect(technicalDetails.open).toBe(false);
    technicalDetails.querySelector('summary')!.click();
    expect(technicalDetails.open).toBe(true);
    expect(Array.from(technicalDetails.querySelectorAll('h3'), (heading): string => heading.textContent!)).toEqual(['Endpoints', 'Discovery', 'Identity']);
    expect(Array.from(technicalDetails.querySelectorAll('dt'), (term): string => term.textContent!)).toEqual([
      'Shared endpoint', 'Dedicated endpoint', 'Downstream endpoint',
      'Discovery detail', 'Last attempt', 'Last success', 'Connector ID', 'Tool name prefix'
    ]);
    expect(technicalDetails.querySelector('button[aria-label="Copy connector ID"]')?.parentElement?.querySelector('code')?.textContent).toBe('b');
    expect(get).toHaveBeenLastCalledWith('b');
    await unmount(component!);
    component = undefined;
  }
  expect(get).toHaveBeenCalledTimes(2);
  expect(goto).not.toHaveBeenCalled();
});

function openApiConnector(id: string): OpenApiConnectorListItem {
  return { id, name: `OpenAPI ${id}`, toolNamePrefix: id, capabilityDescription: `Description ${id}`, publicationStatus: 'Draft', canPublish: true, canUnpublish: false, canImport: true, createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-02T00:00:00Z', tools: [] };
}

test.each(['tools', 'prompts'])('OpenAPI refreshed data for A reloads shallow-selected B on %s without changing the URL', async (capability): Promise<void> => {
  navigation.path = '/admin/openapi-connectors';
  navigation.capability = capability;
  const get = vi.spyOn(OpenApiConnectorDetailsBrowserRoute.prototype, 'get').mockResolvedValue({ connector: openApiConnector('b'), invocationPolicies: [] });
  vi.spyOn(OpenApiConnectorToolsBrowserRoute.prototype, 'list').mockResolvedValue([]);
  for (let refresh = 0; refresh < 2; refresh += 1) {
    component = mount(OpenApiConnectorList, { target: document.body, props: {
      data: { status: 'ready', connectors: [openApiConnector('a'), openApiConnector('b')], selectedConnectorId: 'a', selectedDetail: openApiConnector('a'), selectedDetailFailed: true, invocationPolicies: [{ tool_id: 'a-tool', mode: 'ask', revision: 1 }] },
      onconfigure: (): void => {}
    } });
    await vi.waitFor(() => expect(document.querySelector('#selected-openapi-connector-heading')?.textContent).toBe('OpenAPI b'));
    await vi.waitFor(() => expect(document.body.textContent).toContain('Description b'));
    expect(document.body.textContent).not.toContain('Description a');
    const indicators = document.querySelector('[aria-label="Connector indicators"]');
    expect(Array.from(indicators?.querySelectorAll('dt') ?? [], (term): string => term.textContent!.trim())).toEqual(['Updated']);
    expect(indicators?.querySelector('time')?.dateTime).toBe('2026-01-02T00:00:00.000Z');
    expect(document.querySelector('[aria-label="Status spotlight"]')).toBeNull();
    expect(get).toHaveBeenLastCalledWith('b', expect.any(AbortSignal));
    await unmount(component!);
    component = undefined;
  }
  expect(get).toHaveBeenCalledTimes(2);
  expect(goto).not.toHaveBeenCalled();
});
