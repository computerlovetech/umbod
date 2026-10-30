import { afterEach, describe, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import type { DownstreamMcpConnectorsRoute } from '$lib/admin/downstream-mcp-connectors-api';
import DownstreamMcpWorkspace from './DownstreamMcpWorkspace.svelte';
import { DownstreamMcpMutationState } from './downstream-mcp-mutation-state.svelte';
import { DownstreamMcpWorkspaceState, type DownstreamMcpWorkspaceBundle } from './downstream-mcp-workspace-state.svelte';

vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/admin/downstream-mcp-connectors?capability=tools') } }));
vi.mock('$app/navigation', () => ({ goto: vi.fn(), invalidateAll: vi.fn() }));
vi.mock('$lib/components/feedback', () => ({ useToast: (): object => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }) }));

function grafanaBundle(published: boolean): DownstreamMcpWorkspaceBundle {
  return {
    mode: 'shared',
    connector: {
      connector_id: 'grafana', display_name: 'Grafana', tool_name_prefix: 'grafana', icon_url: '',
      capability_description: 'Grafana tools', base_capability_description: 'Grafana tools', effective_capability_description: 'Grafana tools',
      capability_description_override: { state: 'system', revision: 0 },
      endpoint_url: 'https://grafana.test/mcp', public_path: '/mcp/proxies/grafana', public_url: 'https://umbod.test/mcp/proxies/grafana',
      auth_mode: 'none', authorization_mode: 'shared', header_type: 'bearer', custom_header_name: null, credential_configured: false,
      publication_status: published ? 'published' : 'unpublished', health: { status: 'healthy', checked_at: '2026-01-01T00:00:00Z', reason: null }
    },
    catalog: {
      discovered_at: '2026-01-01T00:00:00Z',
      tools: [{ name: 'search_dashboards', title: 'Search dashboards', description: 'Find dashboards', input_schema: {}, output_schema: null, activation_status: 'enabled' }]
    },
    promptCatalog: { prompts: [], available_actions: [] },
    resourceCatalog: { resources: [], availableActions: [] }
  };
}

function button(label: string, scope: ParentNode = document): HTMLButtonElement {
  const result = Array.from(scope.querySelectorAll('button')).find((candidate) => candidate.textContent?.trim() === label || candidate.getAttribute('aria-label') === label);
  if (!result) throw new Error(`Button not found: ${label}`);
  return result;
}

type MutationApi = Pick<DownstreamMcpConnectorsRoute, 'publish' | 'unpublish' | 'delete' | 'list'>;

function mutationApi(bundle: DownstreamMcpWorkspaceBundle): { [Key in keyof MutationApi]: ReturnType<typeof vi.fn<MutationApi[Key]>> } {
  return {
    publish: vi.fn<MutationApi['publish']>().mockResolvedValue({ ...bundle.connector, publication_status: 'published' }),
    unpublish: vi.fn<MutationApi['unpublish']>().mockResolvedValue({ ...bundle.connector, publication_status: 'unpublished' }),
    delete: vi.fn<MutationApi['delete']>().mockResolvedValue(undefined),
    list: vi.fn<MutationApi['list']>().mockResolvedValue({ connectors: [bundle.connector] })
  };
}

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.clearAllMocks();
});

function renderWorkspace(published: boolean): { api: ReturnType<typeof mutationApi>; navigate: ReturnType<typeof vi.fn>; state: DownstreamMcpWorkspaceState } {
  const bundle = grafanaBundle(published);
  const api = mutationApi(bundle);
  const navigate = vi.fn();
  const operations = new DownstreamMcpMutationState(api, navigate);
  const state = new DownstreamMcpWorkspaceState(undefined, undefined, bundle, undefined, undefined, undefined, undefined, undefined, operations);
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(DownstreamMcpWorkspace, {
    target,
    props: { connectors: [bundle.connector], selected: bundle.connector, catalog: bundle.catalog, state }
  });
  flushSync();
  return { api, navigate, state };
}

async function openConfirmation(label: string): Promise<HTMLElement> {
  button('Open actions for Grafana').click();
  await tick();
  button(label, document.querySelector('[role="menu"]')!).click();
  await tick();
  const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
  expect(dialog?.textContent).toContain(`${label} Grafana?`);
  if (!dialog) throw new Error('Publication confirmation is missing');
  return dialog;
}

describe('shared MCP publication from the action menu', (): void => {
  test.each([
    { label: 'Publish', published: false, action: 'publish', otherAction: 'unpublish' },
    { label: 'Unpublish', published: true, action: 'unpublish', otherAction: 'publish' }
  ] as const)('dispatches $label exactly once after confirmation for a healthy discovered connector', async ({ label, published, action, otherAction }): Promise<void> => {
    const { api, navigate } = renderWorkspace(published);
    const dialog = await openConfirmation(label);
    expect(api[action]).not.toHaveBeenCalled();
    expect(api.list).not.toHaveBeenCalled();
    expect(document.querySelector('[role="menu"]')).toBeNull();

    const confirm = button(label, dialog);
    confirm.click();
    confirm.click();
    await tick();

    expect(document.querySelector('[role="dialog"]')).toBeNull();
    await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith('grafana'));
    expect(api[action]).toHaveBeenCalledExactlyOnceWith('grafana');
    expect(api[otherAction]).not.toHaveBeenCalled();
    expect(api.list).toHaveBeenCalledOnce();
  });

  test('cancelling publication never dispatches an operation', async (): Promise<void> => {
    const { api, navigate } = renderWorkspace(false);
    const dialog = await openConfirmation('Publish');

    button('Cancel', dialog).click();
    await tick();

    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(api.publish).not.toHaveBeenCalled();
    expect(api.list).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
  });

  test('shows pending feedback and blocks competing mutations until publication completes', async (): Promise<void> => {
    const { api, navigate, state } = renderWorkspace(false);
    let complete!: (value: Awaited<ReturnType<MutationApi['publish']>>) => void;
    api.publish.mockImplementation(() => new Promise((resolve) => { complete = resolve; }));
    const dialog = await openConfirmation('Publish');

    button('Publish', dialog).click();
    await tick();

    expect(document.querySelector('[role="status"]')?.textContent).toContain('Updating MCP connector');
    expect(state.operations.locked).toBe(true);
    expect(api.list).not.toHaveBeenCalled();
    button('Open actions for Grafana').click();
    await tick();
    expect(button('Publish', document.querySelector('[role="menu"]')!).disabled).toBe(true);
    state.requestPublication(grafanaBundle(false).connector);
    await state.operations.confirm();
    expect(api.publish).toHaveBeenCalledOnce();

    complete(grafanaBundle(true).connector);
    await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith('grafana'));
  });

  test.each([
    { error: new NetworkError(new Error('private diagnostic')), message: 'outcome is unknown' },
    { error: new HttpError(409, '', { detail: { code: 'public_tool_name_conflict', message: 'conflict', phase: 'publication', retryable: false, context: {} } }), message: 'Publication conflicts with an existing public tool name.' },
    { error: new HttpError(401, '', {}), message: 'Administration access was lost' }
  ])('presents publication errors without silently retrying', async ({ error, message }): Promise<void> => {
    const { api, navigate } = renderWorkspace(false);
    api.publish.mockRejectedValue(error);
    const dialog = await openConfirmation('Publish');

    button('Publish', dialog).click();
    await tick();

    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toContain(message));
    expect(document.body.textContent).not.toContain('private diagnostic');
    expect(api.publish).toHaveBeenCalledOnce();
    expect(api.list).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
    expect(document.querySelector('[role="status"]')).toBeNull();
  });
});
