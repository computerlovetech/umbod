import { readFileSync } from 'node:fs';
import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import type { DownstreamMcpConnector, DownstreamMcpTool } from '$lib/admin/downstream-mcp-connectors';
import { AdminApi } from '$lib/admin/infrastructure/admin-api';
import { HttpError, type Transport, type TransportRequest } from '$lib/admin/infrastructure/transport';
import { downstreamMcpConnectorsOperations } from '$lib/admin/operations/downstream-mcp-connectors';
import { serverFixture } from '$lib/admin/personal-mcp-servers/fixtures.test-support';
import DownstreamMcpWorkspace from '$lib/components/admin/downstream-mcp-connectors/DownstreamMcpWorkspace.svelte';
import DownstreamMcpSetupModal from '$lib/components/admin/downstream-mcp-connectors/DownstreamMcpSetupModal.svelte';
import DownstreamMcpToolActivationToggle from '$lib/components/admin/downstream-mcp-connectors/DownstreamMcpToolActivationToggle.svelte';
import OpenApiToolActivationToggle from '$lib/components/admin/openapi-connectors/OpenApiToolActivationToggle.svelte';
import { DownstreamMcpWorkspaceState, type DownstreamMcpWorkspaceBundle } from '$lib/components/admin/downstream-mcp-connectors/downstream-mcp-workspace-state.svelte';

vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/admin/downstream-mcp-connectors?capability=tools') } }));
vi.mock('$app/navigation', () => ({ goto: vi.fn(), invalidateAll: vi.fn() }));
vi.mock('$lib/components/feedback', () => ({ useToast: (): object => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }) }));

function sharedConnector(): DownstreamMcpConnector {
  return { ...serverFixture('internal-shared-id'), display_name: 'Shared records', authorization_mode: 'shared', auth_mode: 'none' };
}

class RecordingTransport implements Transport {
  readonly requests: TransportRequest<unknown>[] = [];

  constructor(private readonly responses: unknown[]) {}

  async request<T>(request: TransportRequest<T>): Promise<T> {
    request.inputSchema?.parse(request.body);
    this.requests.push(request);
    if (this.responses.length === 0) throw new Error('Unexpected request');
    const response = this.responses.shift();
    if (response instanceof Error) throw response;
    return request.outputSchema ? request.outputSchema.parse(response) : undefined as T;
  }
}

function createForm(): FormData {
  const data = new FormData();
  for (const [name, value] of Object.entries({ displayName: 'Shared records', toolNamePrefix: 'records', capabilityDescription: 'Search records', endpointUrl: 'https://provider.test/mcp', publicPath: 'records', authMode: 'none' })) data.set(name, value);
  return data;
}

const tool: DownstreamMcpTool = { name: 'search_records', title: 'Search records', description: 'Find records', input_schema: {}, output_schema: null, activation_status: 'enabled' };

function workspace(connector: DownstreamMcpConnector, connectors: DownstreamMcpConnector[] = [connector]): string {
  const bundle: DownstreamMcpWorkspaceBundle = connector.authorization_mode === 'personal'
    ? { mode: 'personal', connector }
    : { mode: 'shared', connector, catalog: { discovered_at: null, tools: [tool] }, promptCatalog: { prompts: [], available_actions: [] }, resourceCatalog: { resources: [], availableActions: [] } };
  const state = new DownstreamMcpWorkspaceState(undefined, undefined, bundle);
  state.setMenuOpen(true);
  try {
    return render(DownstreamMcpWorkspace, { props: { connectors, selected: connector, catalog: bundle.catalog, state } }).body;
  } finally {
    state.operations.dispose();
  }
}

function setup(mode: 'create' | 'configure', connector: DownstreamMcpConnector = sharedConnector(), submitting = false, message?: string): string {
  const state = new DownstreamMcpWorkspaceState();
  state.open(mode, { focus(): void {} } as unknown as HTMLElement, mode === 'configure' ? connector : undefined);
  if (submitting) state.beginSubmit();
  try {
    return render(DownstreamMcpSetupModal, { props: { state, connector: mode === 'configure' ? connector : undefined, message } }).body;
  } finally {
    state.operations.dispose();
  }
}

function input(body: string, name: string): string {
  const tag = body.match(new RegExp(`<input\\b[^>]*name="${name}"[^>]*>`))?.[0];
  if (!tag) throw new Error(`Input missing: ${name}`);
  return tag;
}

const controls = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpWorkspace.svelte', 'utf8');
const page = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpPageContent.svelte', 'utf8');
const pageRoute = readFileSync('src/routes/admin/downstream-mcp-connectors/+page.svelte', 'utf8');
const toolCatalog = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpToolCatalog.svelte', 'utf8');

describe('downstream MCP connector administration', () => {
  test('personal selection keeps common details and actions without shared readiness, proxy instructions or catalogues', (): void => {
    const personal = workspace(serverFixture());
    expect(personal).toContain('Personal server');
    expect(personal).toContain('Search records');
    expect(personal).toContain('Registration path');
    expect(personal).toContain('Unpublished');
    expect(personal).toContain('>Publish</button>');
    expect(personal).toContain('>Delete</button>');
    expect(personal).toContain('href="/dashboard"');
    expect(personal).toContain("do not show a user's authorization or private inventory");
    for (const absent of ['Discovery health', 'Bearer token missing', '0 tools', 'Search tools', 'Shared endpoint', 'Dedicated endpoint', '>Configure</button>', 'Refresh discovery', 'Edit capability description', 'title="Copy URI"']) expect(personal).not.toContain(absent);

    const shared = workspace(sharedConnector());
    for (const present of ['Discovery health', 'Discovered tools', 'Search tools', '>Configure</button>', 'Refresh discovery', 'Edit capability description', '>Publish</button>', '>Delete</button>']) expect(shared).toContain(present);
    expect(shared).not.toContain('Personal OAuth settings');
  });

  test('captures and displays the connector capability description', async (): Promise<void> => {
    const body = setup('create');
    expect(input(body, 'capabilityDescription')).toContain('required');
    expect(body).toContain('Default capability description');
    expect(workspace(sharedConnector())).toContain('Search records');
    const transport = new RecordingTransport([sharedConnector()]);
    await downstreamMcpConnectorsOperations.create(new AdminApi(transport), createForm());
    expect(transport.requests).toHaveLength(1);
    expect(transport.requests[0].body).toMatchObject({ metadata: { capability_description: 'Search records' } });
  });

  test('offers publication and per-tool activation controls with pending and error feedback', (): void => {
    expect(workspace(sharedConnector())).toContain('>Publish</button>');
    expect(workspace({ ...sharedConnector(), publication_status: 'published' })).toContain('>Unpublish</button>');
    const body = workspace(sharedConnector());
    for (const label of ['Search tools', 'Tools per page', 'search_records activation', 'Save tools']) expect(body).toContain(label);
    const toggle = render(DownstreamMcpToolActivationToggle, { props: { tool, disabled: true, onActivationChange: (): void => {} } }).body;
    const openApiToggle = render(OpenApiToolActivationToggle, { props: { operationId: tool.name, activationStatus: 'enabled', disabled: true, onActivationChange: (): void => {} } }).body;
    for (const rendered of [toggle, openApiToggle]) {
      expect(rendered).toContain('type="checkbox"');
      expect(rendered).toContain('checked');
      expect(rendered).toContain('disabled');
      expect(rendered).toContain('aria-label="search_records activation"');
    }
    expect(toolCatalog).toContain('onActivationChange={catalog.setToolActivation}');
    expect(toolCatalog).toContain('saveToolActivations');
    expect(toolCatalog).toContain('catalog.beginSave()');
    expect(toolCatalog).toContain('catalog.finishSave(');
  });

  test('uses the shared connector sidebar without exposing connector identifiers', (): void => {
    const shared = sharedConnector();
    const personal = serverFixture('internal-personal-id');
    const body = workspace(shared, [shared, personal]);
    const sidebar = body.match(/<button[^>]*aria-pressed="(?:true|false)"[^>]*>[\s\S]*?<\/button>/g)?.join('');
    expect(sidebar).toBeDefined();
    expect(sidebar).toContain('Shared records');
    expect(sidebar).toContain('Personal server');
    expect(sidebar).toContain('Shared authorization');
    expect(sidebar).toContain('Personal authorization');
    expect(sidebar).toContain('unpublished');
    expect(sidebar).not.toContain(shared.connector_id);
    expect(sidebar).not.toContain(personal.connector_id);
    expect(controls).toContain('ConnectorSidebarList');
  });

  test('resets connector-specific tool catalog state when selection changes', (): void => {
    expect(controls).toContain('{#key detailSelected.connector_id}');
    expect(controls).toContain('connectorId={detailSelected.connector_id} tools={catalog?.tools ?? []}');
  });

  test('recreates page state only when server data changes', (): void => {
    expect(pageRoute).toContain('{#key data}');
    expect(pageRoute).toContain('<DownstreamMcpPageContent {data} {form} />');
    expect(pageRoute).not.toContain('$effect');
    expect(page).not.toContain('$effect');
  });

  test('shares one create and configure form with the canonical proxy prefix', (): void => {
    for (const mode of ['create', 'configure'] as const) {
      const body = setup(mode);
      expect(body).toContain(`data-operation="${mode}"`);
      expect(body).toContain('/mcp/proxies/');
      expect(body).not.toContain('Connector ID');
      for (const name of ['displayName', 'toolNamePrefix', 'capabilityDescription', 'endpointUrl', 'publicPath', 'authMode']) expect(input(body, name)).toBeDefined();
      expect(input(body, 'publicPath')).not.toContain('pattern="/mcp/');
      if (mode === 'configure') expect(input(body, 'connectorId')).toContain('value="internal-shared-id"');
      else expect(body).not.toContain('name="connectorId"');
    }
    expect(page).not.toContain('name="publicPath"');
    expect(page).toContain('<DownstreamMcpWorkspace');
  });

  test('distinguishes the shared aggregate endpoint from the immutable dedicated path', (): void => {
    const create = setup('create');
    expect(create).toContain('Dedicated MCP path (additional)');
    expect(create).toMatch(/<span[^>]*aria-hidden="true"[^>]*>\/mcp\/proxies\//);
    expect(input(create, 'publicPath')).toContain('pattern="[a-z0-9][a-z0-9-]{0,62}"');
    expect(input(create, 'publicPath')).toContain('maxlength="63"');
    expect(input(create, 'publicPath')).toContain('required');
    expect(input(create, 'publicPath')).not.toContain('readonly');
    expect(create).toMatch(/After discovery, enable and publish tools to make them available on <code[^>]*>\/mcp<\/code>/);
    expect(create).toContain('Enter only the connector-specific suffix');
    const configure = setup('configure');
    expect(configure).toContain('The dedicated MCP path is immutable');
    expect(input(configure, 'publicPath')).toContain('readonly');
    expect(input(configure, 'publicPath')).toContain('value="internal-shared-id"');
    const detail = workspace(sharedConnector());
    expect(detail).toContain('Shared endpoint');
    expect(detail).toContain('aria-label="Copy https://umbod.test/mcp"');
    expect(detail).toContain('Dedicated endpoint');
    expect(detail).toContain('aria-label="Copy https://umbod.test/mcp/proxies/internal-shared-id"');
    for (const absent of ['namespaced alongside tools from other connectors', 'Only this connector’s tools appear here, using their original downstream names', 'Public MCP path']) expect(detail).not.toContain(absent);
  });

  test('uses shared accessible form controls and retains configured bearer secrets', (): void => {
    const connector = { ...sharedConnector(), auth_mode: 'static_bearer' as const, credential_configured: true };
    const configured = setup('configure', connector);
    expect(configured).toContain('aria-label="Authentication"');
    expect(input(configured, 'authMode')).toContain('value="static_bearer"');
    expect(configured).not.toContain('<select');
    const token = input(configured, 'bearerToken');
    expect(token).toContain('type="password"');
    expect(token).toContain('autocomplete="new-password"');
    expect(token).not.toContain('required');
    expect(token).toContain('value=""');
    expect(configured).toContain('Leave blank to keep the existing secret.');
    expect(input(setup('configure', { ...connector, credential_configured: false }), 'bearerToken')).toContain('required');
    expect(setup('create')).not.toContain('name="bearerToken"');
    expect(configured).toContain('for="downstream-mcp-configure-bearer-token"');
    expect(token).toContain('id="downstream-mcp-configure-bearer-token"');
    expect(input(setup('create'), 'displayName')).toContain('id="downstream-mcp-create-display-name"');
    const pending = setup('configure', connector, true, 'Check the configuration values.');
    expect(pending).toMatch(/<button[^>]*disabled[^>]*aria-label="Save connector"[^>]*aria-busy="true"/);
    expect(pending).toContain('role="alert"');
    expect(pending).toContain('Check the configuration values.');
    expect(input(pending, 'publicPath')).toContain('aria-invalid="true"');
  });

  test('routes control actions through the composite API adapter', async (): Promise<void> => {
    const connector = sharedConnector();
    for (const [action, method, publication_status] of [['publish', 'PUT', 'published'], ['unpublish', 'DELETE', 'unpublished']] as const) {
      const transport = new RecordingTransport([connector, { connector_id: connector.connector_id, publication_status }]);
      const publication = new FormData();
      publication.set('connectorId', connector.connector_id);
      expect(await downstreamMcpConnectorsOperations[action](new AdminApi(transport), publication)).toMatchObject({ location: `/admin/downstream-mcp-connectors?connector=${connector.connector_id}` });
      expect(transport.requests).toHaveLength(2);
      expect(transport.requests[1]).toMatchObject({ method, path: `/admin/connectors/mcp/${connector.connector_id}/publication` });
    }
    const activation = { tool_id: tool.name, activation_status: 'enabled', invocation_mode: 'direct', policy_revision: 0 };
    const transport = new RecordingTransport([connector, { connector_id: connector.connector_id, tools: [activation] }]);
    const activations = new FormData();
    activations.set('connectorId', connector.connector_id);
    activations.set('toolActivations', JSON.stringify({ tools: [{ tool_id: tool.name, activation_status: 'enabled' }] }));
    activations.set('invocationPolicies', JSON.stringify({ tools: [] }));
    expect(await downstreamMcpConnectorsOperations.saveToolActivations(new AdminApi(transport), activations)).toMatchObject({ activationResponse: { connector_id: connector.connector_id, tools: [activation] } });
    expect(transport.requests).toHaveLength(2);
    expect(transport.requests[1]).toMatchObject({ method: 'PUT', path: `/admin/connectors/mcp/${connector.connector_id}/tools/activation`, body: { tools: [{ tool_id: tool.name, activation_status: 'enabled' }] } });
    const unhealthy = new RecordingTransport([sharedConnector(), { ...sharedConnector(), health: { status: 'unhealthy', checked_at: null, reason: 'Discovery unavailable' } }]);
    const data = createForm();
    data.set('connectorId', 'internal-shared-id');
    expect(await downstreamMcpConnectorsOperations.refresh(new AdminApi(unhealthy), data)).toMatchObject({ status: 422, data: { status: 'unhealthy', message: 'Discovery unavailable' } });
    expect(unhealthy.requests).toHaveLength(2);

    const invalid = new RecordingTransport([]);
    data.set('publicPath', '/mcp');
    data.set('endpointUrl', 'http://insecure.test/mcp');
    expect(await downstreamMcpConnectorsOperations.create(new AdminApi(invalid), data)).toMatchObject({ status: 422, data: { status: 'invalid', mode: 'create' } });
    expect(invalid.requests).toHaveLength(0);

    const rejected = new RecordingTransport([new HttpError(422, '', { detail: 'private-validation-sentinel' })]);
    const secret = createForm();
    secret.set('authMode', 'static_bearer');
    secret.set('bearerToken', 'private-token-sentinel');
    const failure = await downstreamMcpConnectorsOperations.create(new AdminApi(rejected), secret);
    expect(failure).toMatchObject({ data: { mode: 'create', status: 'failed' } });
    expect(JSON.stringify(failure)).not.toContain('private-validation-sentinel');
    expect(JSON.stringify(failure)).not.toContain('private-token-sentinel');
    expect(rejected.requests).toHaveLength(1);
  });
});
