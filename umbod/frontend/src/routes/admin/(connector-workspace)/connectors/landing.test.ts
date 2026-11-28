import { afterEach, describe, expect, test, vi } from 'vitest';
import type { ConnectorApiItem } from '#lib/admin/connectors.js';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import { summaryFixture } from '#lib/admin/personal-mcp-servers/fixtures.test-support.js';
import { submittedConnector } from '#lib/admin/portable-connectors/fixtures.test-support.js';
import { load } from './+page';
import { load as loadPortable } from '../portable-connectors/+page';

type LoadEvent = Parameters<typeof load>[0];

const api = vi.hoisted(() => ({ native: vi.fn(), openapi: vi.fn(), mcp: vi.fn(), portable: vi.fn(), getNative: vi.fn() }));
vi.mock('#lib/admin/infrastructure/admin-api.js', () => ({ adminApi: () => ({
  connectors: {
    connectors: { list: api.native, get: api.getNative, getConfiguration: vi.fn() },
    tools: { listActivations: vi.fn() },
    prompts: { list: vi.fn() },
    resources: { list: vi.fn() }
  },
  openApiConnectors: { connectors: { list: api.openapi } },
  downstreamMcpConnectors: { list: api.mcp },
  portableConnectors: { list: async (): Promise<{ connectors: typeof submittedConnector[] }> => api.portable() ?? { connectors: [] } }
}) }));

afterEach(() => vi.resetAllMocks());

function nativeConnector(id: string, displayName: string, publicationStatus: ConnectorApiItem['publication_status']): ConnectorApiItem {
  return { id, display_name: displayName, description: '', extension: { source: 'built-in' }, publication_status: publicationStatus, available_actions: [] };
}

function loadLanding(query = ''): ReturnType<typeof load> {
  return load({ url: new URL(`https://umbod.test/admin/connectors${query}`), fetch: vi.fn() } as unknown as LoadEvent);
}

describe('connector workspace landing', () => {
  test('opens the first visible MCP connector rather than an unconfigured native entry', async (): Promise<void> => {
    api.native.mockResolvedValue({ connectors: [nativeConnector('setup', 'Aardvark', 'unconfigured'), nativeConnector('zebra', 'Zebra', 'published')] });
    api.openapi.mockResolvedValue({ connectors: [] });
    api.mcp.mockResolvedValue({ connectors: [{ ...summaryFixture('mcp-z'), display_name: 'Yak' }, { ...summaryFixture('mcp-a'), display_name: 'Alpaca' }] });

    await expect(loadLanding('?capability=resources')).rejects.toMatchObject({ status: 307, location: '/admin/downstream-mcp-connectors?connector=mcp-a&capability=resources' });
    expect(api.getNative).not.toHaveBeenCalled();
  });

  test('opens OpenAPI when the native inventory fails', async (): Promise<void> => {
    api.native.mockRejectedValue(new HttpError(503, 'Unavailable', {}));
    api.openapi.mockResolvedValue({ connectors: [{ connector_id: 'billing', display_name: 'Billing', publication_status: 'draft', available_actions: [] }] });
    api.mcp.mockResolvedValue({ connectors: [] });

    await expect(loadLanding()).rejects.toMatchObject({ status: 307, location: '/admin/openapi-connectors?connector=billing' });
  });

  test('selects native connectors by displayed order unless a deep link names another', async (): Promise<void> => {
    api.native.mockResolvedValue({ connectors: [nativeConnector('zebra', 'Zebra', 'published'), nativeConnector('alpaca', 'Alpaca', 'published')] });
    api.openapi.mockResolvedValue({ connectors: [] });
    api.mcp.mockResolvedValue({ connectors: [{ ...summaryFixture(), display_name: 'Bison' }] });
    api.getNative.mockRejectedValue(new HttpError(503, 'Unavailable', {}));

    await expect(loadLanding()).resolves.toMatchObject({ selectedConnectorId: 'alpaca', selectedDetailFailed: true });
    await expect(loadLanding('?connector=zebra')).resolves.toMatchObject({ selectedConnectorId: 'zebra', selectedDetailFailed: true });
    expect(api.getNative.mock.calls).toEqual([['alpaca'], ['zebra']]);
  });

  test('keeps native setup on the native route even when the first visible connector is MCP', async (): Promise<void> => {
    api.native.mockResolvedValue({ connectors: [nativeConnector('setup', 'New native connector', 'unconfigured')] });
    api.openapi.mockResolvedValue({ connectors: [] });
    api.mcp.mockResolvedValue({ connectors: [summaryFixture()] });

    await expect(loadLanding('?setup=native')).resolves.toMatchObject({ nativeAvailable: true, unifiedRows: [{ kind: 'mcp' }] });
    expect(api.getNative).not.toHaveBeenCalled();
  });

  test('lands on the configuration route when only a portable submission is present', async (): Promise<void> => {
    api.native.mockResolvedValue({ connectors: [] });
    api.openapi.mockResolvedValue({ connectors: [] });
    api.mcp.mockResolvedValue({ connectors: [] });
    api.portable.mockResolvedValue({ connectors: [submittedConnector] });

    const location = `/admin/portable-connectors?connector=${submittedConnector.connector_id}`;
    await expect(loadLanding()).rejects.toMatchObject({ status: 307, location });
    await expect(loadPortable({ url: new URL(location, 'https://umbod.test'), fetch: vi.fn() } as unknown as Parameters<typeof loadPortable>[0]))
      .resolves.toMatchObject({ selected: { id: submittedConnector.connector_id, kind: 'portable', configured: false } });
    expect(api.getNative).not.toHaveBeenCalled();
  });

  test('leaves a genuinely empty mixed inventory unselected', async (): Promise<void> => {
    api.native.mockResolvedValue({ connectors: [] });
    api.openapi.mockResolvedValue({ connectors: [] });
    api.mcp.mockResolvedValue({ connectors: [] });

    await expect(loadLanding()).resolves.toMatchObject({ unifiedRows: [], unavailableKinds: [], nativeAvailable: false });
    expect(api.getNative).not.toHaveBeenCalled();
  });
});
