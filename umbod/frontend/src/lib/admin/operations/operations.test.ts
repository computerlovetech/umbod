import { describe, expect, test } from 'vitest';
import { AdminApi } from '../infrastructure/admin-api';
import { AuthenticationRequiredError, HttpError, type Transport, type TransportRequest } from '../infrastructure/transport';
import { connectorsOperations } from './connectors';
import { groupPermissionsOperations } from './group-permissions';
import { openApiConnectorsOperations } from './openapi-connectors';
import { OperationFailure, OperationRedirect } from './contracts';

class InMemoryOperationTransport implements Transport {
  readonly requests: TransportRequest<unknown>[] = [];
  constructor(private readonly responses: unknown[]) {}
  async request<T>(request: TransportRequest<T>): Promise<T> {
    this.requests.push(request);
    request.inputSchema?.parse(request.body);
    const response = this.responses.shift();
    if (response instanceof Error) throw response;
    return request.outputSchema ? request.outputSchema.parse(response) : undefined as T;
  }
}

function form(values: Record<string, string>): FormData {
  const data = new FormData();
  for (const [name, value] of Object.entries(values)) data.set(name, value);
  return data;
}

function setupForm(): FormData {
  return form({ displayName: 'Billing', toolNamePrefix: 'billing', capabilityDescription: 'Manage billing', approvedHostname: 'api.example.test', authenticationType: 'none', importMode: 'url', document: JSON.stringify({ openapi: '3.1.0', paths: {} }) });
}

const connector = {
  connector_id: 'billing', display_name: 'Billing', tool_name_prefix: 'billing', capability_description: 'Manage billing', base_capability_description: 'Manage billing', effective_capability_description: 'Manage billing',
  capability_description_override: { state: 'system', revision: 0 }, created_at: '2026-01-01', updated_at: '2026-01-01', publication_status: 'draft', available_actions: ['publish']
};

describe('typed browser administration operations', () => {
  test('sets up an OpenAPI connector with one validated backend request', async () => {
    const transport = new InMemoryOperationTransport([connector]);
    const result = await openApiConnectorsOperations.setup(new AdminApi(transport), setupForm());
    expect(result).toBeInstanceOf(OperationRedirect);
    expect(transport.requests).toHaveLength(1);
    expect(transport.requests[0]).toMatchObject({ method: 'POST', path: '/admin/connectors/openapi/setup', body: { display_name: 'Billing', document: { openapi: '3.1.0', paths: {} }, approved_hosts: ['api.example.test'], authentication_type: 'none', bearer_token: '' } });
  });
  test('surfaces cleanup failure with connector identity and no compensating browser requests', async () => {
    const transport = new InMemoryOperationTransport([new HttpError(503, 'Unavailable', { detail: { code: 'openapi_setup_cleanup_failed', connector_id: 'billing' } })]);
    expect(await openApiConnectorsOperations.setup(new AdminApi(transport), setupForm())).toMatchObject({ status: 'warning', connectorId: 'billing', retryable: false });
    expect(transport.requests).toHaveLength(1);
  });
  test.each(['text/plain', 'application/json'])('rejects invalid file contents before connector creation (%s)', async (type) => {
    const transport = new InMemoryOperationTransport([]);
    const data = setupForm(); data.set('importMode', 'file'); data.set('file', new File(['not json'], 'catalog.json', { type }));
    expect(await openApiConnectorsOperations.setup(new AdminApi(transport), data)).toMatchObject({ status: 'invalid' });
    expect(transport.requests).toHaveLength(0);
  });
  test('parses valid file mode into the setup JSON contract', async () => {
    const transport = new InMemoryOperationTransport([connector]);
    const data = setupForm(); data.set('importMode', 'file'); data.set('file', new File(['{"openapi":"3.1.0","paths":{}}'], 'catalog.json', { type: 'application/json' }));
    expect(await openApiConnectorsOperations.setup(new AdminApi(transport), data)).toBeInstanceOf(OperationRedirect);
    expect(transport.requests[0].body).toMatchObject({ document: { openapi: '3.1.0', paths: {} } });
  });
  test('preserves safe configuration values without echoing secrets after failure', async () => {
    const transport = new InMemoryOperationTransport([new HttpError(422, 'Invalid', { detail: 'Rejected' })]);
    const data = form({ connectorId: 'billing', host: 'api.example.test', token: 'private-token', __secret_fields: 'token' });
    const result = await connectorsOperations.saveConfiguration(new AdminApi(transport), data);
    expect(result).toMatchObject({ status: 'failed', values: { host: 'api.example.test' } });
    expect(JSON.stringify(result)).not.toContain('private-token');
  });
  test('preserves exact group identifiers while rejecting invalid permissions before transport', async () => {
    const transport = new InMemoryOperationTransport([]);
    const api = new AdminApi(transport);
    expect(await groupPermissionsOperations.saveGroupPermissions(api, form({ groupId: 'Engineering', permissionSet: 'invalid' }))).toMatchObject({ status: 'rejected', groupId: 'Engineering' });
    expect(transport.requests).toHaveLength(0);
    expect(await groupPermissionsOperations.registerPermissionGroup(api, form({ groupId: 'Engineering' }))).toMatchObject({ status: 'registered', groupId: 'Engineering' });
    expect(transport.requests[0].path).toBe('/admin/mcp-permissions/groups/Engineering');
  });
  test('reconciles a failed native tool save from authoritative backend activation state', async () => {
    const transport = new InMemoryOperationTransport([new HttpError(503, 'Unavailable', null), { connector_id: 'billing', tools: [{ tool_id: 'invoice', activation_status: 'disabled', invocation_mode: 'ask', policy_revision: 2 }] }]);
    const result = await connectorsOperations.saveToolActivations(new AdminApi(transport), form({ connectorId: 'billing', toolActivations: '[{"operationName":"invoice","activationStatus":"enabled"}]', invocationPolicies: '{"tools":[]}' }));
    expect(result).toBeInstanceOf(OperationFailure);
    expect(result).toMatchObject({ status: 503, data: { authoritativeActivationResponse: { tools: [{ tool_id: 'invoice', activation_status: 'disabled' }] } } });
  });
  test('does not turn expired mutations into retryable operational failures', async () => {
    const transport = new InMemoryOperationTransport([new AuthenticationRequiredError()]);
    await expect(connectorsOperations.publish(new AdminApi(transport), form({ connectorId: 'billing' }))).rejects.toBeInstanceOf(AuthenticationRequiredError);
  });
});
