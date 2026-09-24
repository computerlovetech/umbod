import { describe, expect, test, vi } from 'vitest';
import { load } from './+page.server';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init
  });
}

function loadEvent(fetch: typeof globalThis.fetch): Parameters<typeof load>[0] {
  return {
    fetch,
    request: new Request('http://frontend/admin/group-permissions', {
      headers: { 'X-Auth-Request-Access-Token': 'proxy-jwt' }
    })
  } as Parameters<typeof load>[0];
}

describe('/admin/group-permissions server load', () => {
  test('does not request detail or targets when summaries are empty', async () => {
    const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const path = String(url);
      if (path.endsWith('/groups')) {
        return jsonResponse({ groups: [] });
      }
      return jsonResponse({ connectors: [], capabilities: [] });
    });

    await load(loadEvent(fetch as unknown as typeof globalThis.fetch));

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0]?.[1]).toMatchObject({ method: 'GET', headers: { authorization: 'proxy-jwt' } });
  });

  test('loads the first ordered group detail and assignable targets in parallel after summaries', async () => {
    let releaseDetail!: () => void;
    let releaseTargets!: () => void;
    const detailGate = new Promise<void>((resolve) => { releaseDetail = resolve; });
    const targetsGate = new Promise<void>((resolve) => { releaseTargets = resolve; });
    const requestedPaths: string[] = [];
    const fetch = vi.fn(async (url: string | URL | Request) => {
      const path = String(url);
      requestedPaths.push(path);
      if (path.endsWith('/groups')) return jsonResponse({ groups: [{ group_id: 'first' }, { group_id: 'second' }] });
      if (path.endsWith('/groups/first')) {
        await detailGate;
        return jsonResponse({ group_id: 'first', connector_ids: [], capabilities: [] });
      }
      if (path.endsWith('/assignable-targets')) {
        await targetsGate;
        return jsonResponse({ connectors: [], capabilities: [] });
      }
      throw new Error(`Unexpected request ${path}`);
    });

    const loading = load(loadEvent(fetch as unknown as typeof globalThis.fetch));
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(requestedPaths[0]).toMatch(/\/groups$/);
    expect(requestedPaths[1]).toMatch(/\/(groups\/first|assignable-targets)$/);
    expect(requestedPaths[2]).toMatch(/\/(groups\/first|assignable-targets)$/);
    releaseDetail();
    releaseTargets();
    await expect(loading).resolves.toMatchObject({ preloadedGroup: { groupId: 'first' }, assignableTargets: [] });
  });

  test.each([401, 403])('preserves backend status %i instead of returning 500', async (status) => {
    const fetch = vi.fn(async () => jsonResponse({ detail: 'Access denied' }, { status, statusText: 'Access denied' }));

    await expect(load(loadEvent(fetch as unknown as typeof globalThis.fetch))).rejects.toMatchObject({ status });
  });
});
