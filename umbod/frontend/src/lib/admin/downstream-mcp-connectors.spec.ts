import { describe, expect, test } from 'vitest';
import type { Transport, TransportRequest } from './infrastructure/transport';
import { DownstreamMcpConnectorsRoute } from './downstream-mcp-connectors-api';
import { downstreamMcpConnectorCreateInputSchema, downstreamMcpConnectorListSchema, downstreamMcpConnectorConfigurationInputSchema, downstreamMcpConnectorSchema, downstreamMcpToolListSchema } from './downstream-mcp-connectors';

function recordingTransport(): { transport: Transport; calls: TransportRequest<unknown>[] } {
  const calls: TransportRequest<unknown>[] = [];
  return { calls, transport: { async request(options) { calls.push(options as TransportRequest<unknown>); return undefined as never; } } };
}

describe('downstream MCP schemas', () => {
  test('requires a validated capability description in create, update, and response DTOs', () => {
    const metadata = { display_name: 'One', tool_name_prefix: 'One', capability_description: 'Search customer records', public_path: '/mcp/proxies/one' };
    const configuration = { endpoint_url: 'https://one.test/mcp', auth_mode: 'none' as const, bearer_token: null };
    expect(downstreamMcpConnectorCreateInputSchema.parse({ metadata, configuration }).metadata.capability_description).toBe('Search customer records');
    expect(downstreamMcpConnectorConfigurationInputSchema.safeParse({ endpoint_url: 'bad', auth_mode: 'none', bearer_token: null }).success).toBe(false);
    expect(downstreamMcpConnectorCreateInputSchema.safeParse({ metadata: { ...metadata, capability_description: 'x'.repeat(301) }, configuration }).success).toBe(false);
  });

  test('rejects exposed credential material in responses', () => {
    expect(() => downstreamMcpConnectorSchema.parse({ connector_id: 'one', display_name: 'One', tool_name_prefix: 'One', capability_description: 'Search records', endpoint_url: 'https://one.test/mcp', auth_mode: 'static_bearer', credential_configured: true, publication_status: 'unpublished', health: { status: 'unknown', checked_at: null, reason: null }, bearer_token: 'secret' })).toThrow();
  });

  test('accepts blank bearer token for update retention', () => {
    expect(downstreamMcpConnectorConfigurationInputSchema.parse({ endpoint_url: 'https://one.test/mcp', auth_mode: 'static_bearer', bearer_token: '' }).bearer_token).toBe('');
  });

  test('rejects unknown static token configuration fields', () => {
    expect(downstreamMcpConnectorConfigurationInputSchema.safeParse({ endpoint_url: 'https://one.test/mcp', auth_mode: 'static_bearer', bearer_token: 'secret', header_typ: 'basic' }).success).toBe(false);
  });

  test('accepts only backend-compatible public proxy paths', () => {
    const metadata = { display_name: 'One', tool_name_prefix: 'One', capability_description: 'Search records' };
    const configuration = { endpoint_url: 'https://one.test/mcp', auth_mode: 'none' as const, bearer_token: null };
    expect(downstreamMcpConnectorCreateInputSchema.safeParse({ metadata: { ...metadata, public_path: '/mcp/proxies/one' }, configuration }).success).toBe(true);
    expect(downstreamMcpConnectorCreateInputSchema.safeParse({ metadata: { ...metadata, public_path: '/mcp/one' }, configuration }).success).toBe(false);
    expect(downstreamMcpConnectorCreateInputSchema.safeParse({ metadata: { ...metadata, public_path: '/mcp/proxies/health' }, configuration }).success).toBe(false);
    expect(downstreamMcpConnectorCreateInputSchema.safeParse({ metadata: { ...metadata, public_path: `/mcp/proxies/${'a'.repeat(64)}` }, configuration }).success).toBe(false);
  });


  test('list and get parse distinct strict contracts while detail retains detail fields', () => {
    const summary = { connector_id: 'one', display_name: 'One', icon_url: '', auth_mode: 'none' as const, publication_status: 'unpublished', health: { status: 'unknown', checked_at: null, reason: null } };
    const detail = { ...summary, tool_name_prefix: 'One', capability_description: 'Search records', base_capability_description: 'Search records', effective_capability_description: 'Search records', capability_description_override: { state: 'system' as const, revision: 0 }, endpoint_url: 'https://one.test/mcp', public_path: '/mcp/proxies/one', public_url: 'https://agent.test/mcp/proxies/one', header_type: 'bearer' as const, custom_header_name: null, credential_configured: false };
    expect(downstreamMcpConnectorListSchema.parse({ connectors: [summary] }).connectors[0]).toEqual(summary);
    expect(downstreamMcpConnectorListSchema.safeParse({ connectors: [detail] }).success).toBe(false);
    expect(downstreamMcpConnectorSchema.parse(detail)).toMatchObject({ endpoint_url: 'https://one.test/mcp', capability_description: 'Search records' });
    expect(downstreamMcpConnectorListSchema.parse({ connectors: [{ ...summary, auth_mode: 'oauth' }] }).connectors[0].auth_mode).toBe('oauth');
  });

  test('requires activation state on discovered tools', () => {
    expect(downstreamMcpToolListSchema.parse({ discovered_at: null, tools: [{ name: 'run', title: 'Run', description: '', input_schema: {}, output_schema: null, activation_status: 'disabled' }] }).tools[0].activation_status).toBe('disabled');
  });
});

describe('downstream MCP route adapter', () => {
  test('encodes ids and exposes publication and activation operations', () => {
    const { transport, calls } = recordingTransport();
    const route = new DownstreamMcpConnectorsRoute(transport);
route.publish('a b'); route.unpublish('a b'); route.saveActivations('a b', [{ toolId: 'tool/run', activationStatus: 'enabled', invocationMode: 'ask', expectedPolicyRevision: 1 }, { toolId: 'tool/read', invocationMode: 'direct', expectedPolicyRevision: 0 }]);
    expect(calls.map((call) => [call.method, call.path])).toEqual([
      ['PUT', '/admin/connectors/mcp/a%20b/publication'],
      ['DELETE', '/admin/connectors/mcp/a%20b/publication'],
      ['PUT', '/admin/connectors/mcp/a%20b/tools/activation']
    ]);
    expect(calls[2].body).toEqual({ tools: [
      { tool_id: 'tool/run', activation_status: 'enabled', invocation_mode: 'ask', expected_policy_revision: 1 },
      { tool_id: 'tool/read', invocation_mode: 'direct', expected_policy_revision: 0 }
    ] });
    expect(calls[2].path).not.toContain('invocation-policy');
    expect('saveInvocationPolicies' in route).toBe(false);
    expect('enableTool' in route).toBe(false);
    expect('disableTool' in route).toBe(false);
  });
});
