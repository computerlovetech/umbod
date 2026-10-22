import { beforeEach, describe, expect, test, vi } from 'vitest';
import { load as personalLoad } from './+page';
import { load as workspaceLoad } from '../downstream-mcp-connectors/+page';
import { serverFixture, summaryFixture } from '$lib/admin/personal-mcp-servers/fixtures.test-support';

const api = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn(), tools: vi.fn(), prompts: vi.fn(), resources: vi.fn(), listActivations: vi.fn() }));
vi.mock('$lib/admin/infrastructure/admin-api', () => ({ adminApi: () => ({ downstreamMcpConnectors: api }) }));
beforeEach(() => vi.clearAllMocks());

describe('unified MCP administration navigation', () => {
  test.each(['connector=personal&capability=tools', 'capability=prompts', 'connector=%2Funsafe&capability=resources'])('redirects old personal route with safe query: %s', async (query) => {
    const expected = query.includes('unsafe') ? 'capability=resources' : query;
    await expect(async () => personalLoad({ url: new URL(`https://umbod.test/admin/personal-mcp-servers?${query}`) } as never)).rejects.toMatchObject({ status: 307, location: `/admin/downstream-mcp-connectors?${expected}` });
    expect(api.list).not.toHaveBeenCalled();
  });
  test('deep-links personal details without requesting shared catalogues or activations', async () => {
    api.list.mockResolvedValue({ connectors: [summaryFixture(), { ...summaryFixture('shared'), authorization_mode: 'shared', auth_mode: 'none' }] });
    api.get.mockResolvedValue(serverFixture());
    const result = await workspaceLoad({ url: new URL('https://umbod.test/admin/downstream-mcp-connectors?connector=personal'), fetch: vi.fn() } as never);
    expect(result).toMatchObject({ selectedConnectorId: 'personal', selectedDetail: serverFixture(), connectors: [summaryFixture(), { connector_id: 'shared' }] });
    expect(api.get).toHaveBeenCalledWith('personal');
    for (const operation of [api.tools, api.prompts, api.resources, api.listActivations]) expect(operation).not.toHaveBeenCalled();
  });
});
