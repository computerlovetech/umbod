import { describe, expect, test, vi } from 'vitest';
import { load as personalLoad } from './+page';
import { load as sharedLoad } from '../downstream-mcp-connectors/+page';
import { serverFixture, summaryFixture } from '$lib/admin/personal-mcp-servers/fixtures.test-support';

const sharedApi = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn(), tools: vi.fn(), prompts: vi.fn(), resources: vi.fn(), listActivations: vi.fn() }));
vi.mock('$lib/admin/infrastructure/admin-api', () => ({ adminApi: () => ({ downstreamMcpConnectors: sharedApi }) }));

describe('personal and shared administration navigation', () => {
  test('personal route retains a selected id without fetching shared bundles', async () => {
    const request = vi.fn();
    const result = await personalLoad({ url: new URL('https://umbod.test/admin/personal-mcp-servers?connector=personal'), fetch: request } as never);
    expect(result).toEqual({ requestedId: 'personal' });
    expect(request).not.toHaveBeenCalled();
  });
  test('a direct personal selection in the shared route never loads personal bundles', async () => {
    sharedApi.list.mockResolvedValue({ connectors: [summaryFixture(), { ...summaryFixture('shared'), authorization_mode: 'shared', auth_mode: 'none' }] });
    sharedApi.get.mockResolvedValue({ ...serverFixture('shared'), authorization_mode: 'shared', auth_mode: 'none' });
    sharedApi.tools.mockResolvedValue({ discovered_at: null, tools: [] });
    sharedApi.prompts.mockResolvedValue({ prompts: [], available_actions: [] });
    sharedApi.resources.mockResolvedValue({ resources: [], available_actions: [] });
    sharedApi.listActivations.mockResolvedValue({ connector_id: 'shared', tools: [] });
    const result = await sharedLoad({ url: new URL('https://umbod.test/admin/downstream-mcp-connectors?connector=personal'), fetch: vi.fn() } as never);
    expect(result).toMatchObject({ selectedConnectorId: 'shared', connectors: [{ connector_id: 'shared' }] });
    for (const operation of [sharedApi.get, sharedApi.tools, sharedApi.prompts, sharedApi.resources, sharedApi.listActivations]) {
      expect(operation).toHaveBeenCalledWith('shared');
      expect(operation).not.toHaveBeenCalledWith('personal');
    }
  });
});
