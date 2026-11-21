import { describe, expect, it, vi } from 'vitest';
import type { McpEndpointAccessResult, McpRegistryPage, McpRegistrySearch, McpRegistryServer } from '#lib/admin/mcp-endpoint-setup.js';
import { AuthenticationRequiredError, HttpError } from '#lib/admin/infrastructure/transport.js';
import type { EndpointDiscoveryResult } from '#lib/admin/personal-mcp-servers/domain/discovery.js';
import { McpEndpointSetupState, type McpSetupDraft, type McpSetupMode } from './mcp-endpoint-setup-state.svelte';

const endpointUrl = 'https://mcp.example.com/mcp';
const anonymous: McpEndpointAccessResult = {
  anonymous_initialization: { kind: 'anonymous_initialization_succeeded' },
  oauth: { kind: 'oauth_not_confirmed' }
};
const rejected: McpEndpointAccessResult = {
  anonymous_initialization: { kind: 'anonymous_access_rejected', status_code: 401 },
  oauth: { kind: 'oauth_not_confirmed' }
};
const inconclusive: McpEndpointAccessResult = {
  anonymous_initialization: { kind: 'inconclusive', reason: 'timeout' },
  oauth: { kind: 'oauth_not_checked' }
};

function setup(personalAvailable = true) {
  const search = vi.fn<(query: McpRegistrySearch) => Promise<McpRegistryPage>>();
  const checkAccess = vi.fn<(url: string) => Promise<McpEndpointAccessResult>>();
  const complete = vi.fn<(mode: McpSetupMode, draft: McpSetupDraft) => void>();
  const accessLost = vi.fn<() => void>();
  const state = new McpEndpointSetupState({ api: () => ({ search, checkAccess }), personalAvailable: () => personalAvailable, complete, accessLost });
  return { state, search, checkAccess, complete, accessLost };
}

function enterManual(state: McpEndpointSetupState, url: string): void {
  state.openManual();
  state.changeManualUrl(url);
}

function registryServer(name: string): McpRegistryServer {
  return {
    name, title: `Title for ${name}`, description: 'Registry description', version: '1.0.0',
    endpoints: [{ url: endpointUrl, required_headers: ['authorization'] }, { url: `${endpointUrl}/alternate`, required_headers: ['x-api-key'] }]
  };
}

describe('MCP endpoint setup state', () => {
  it('keeps the results area compact until the first valid search and expanded between queries', async () => {
    const { state, search } = setup();
    search.mockResolvedValue({ servers: [], next_cursor: '' });
    state.openSearch();
    state.changeTerm('sv');
    await state.search();
    expect(state.hasSearched).toBe(false);
    expect(search).not.toHaveBeenCalled();

    state.changeTerm('svelte');
    const firstSearch = state.search();
    expect(state.hasSearched).toBe(true);
    expect(state.searchStatus).toBe('loading');
    await firstSearch;

    state.changeTerm('');
    expect(state.searchStatus).toBe('idle');
    expect(state.hasSearched).toBe(true);
  });
  it('paginates searches, retries a failed page and only checks the endpoint chosen in review', async () => {
    const { state, search, checkAccess, complete } = setup();
    const first = registryServer('example/first');
    const second = registryServer('example/second');
    search.mockResolvedValueOnce({ servers: [first], next_cursor: 'next' }).mockRejectedValueOnce(new Error()).mockResolvedValueOnce({ servers: [first, second], next_cursor: '' });
    checkAccess.mockResolvedValue(anonymous);
    state.openSearch();
    state.changeTerm('  example  ');
    await state.search();
    await state.loadMore();
    expect(state.searchStatus).toBe('error');
    expect(state.servers).toEqual([first]);
    await state.retrySearch();
    expect(search).toHaveBeenLastCalledWith({ term: 'example', limit: 20, cursor: 'next' });
    expect(state.servers).toEqual([first, second]);
    expect(state.hasMore).toBe(false);
    state.selectServer(second);
    expect(state.step).toBe('search');
    expect(checkAccess).not.toHaveBeenCalled();
    state.review();
    await state.checkAccess();
    expect(checkAccess).not.toHaveBeenCalled();
    state.selectEndpoint(second.endpoints[1]);
    await state.checkAccess();
    expect(checkAccess).toHaveBeenCalledWith(`${endpointUrl}/alternate`);
    expect(state.modes).toContain('none');
    state.finish('none');
    expect(complete).toHaveBeenCalledWith('none', { endpointUrl: `${endpointUrl}/alternate`, displayName: second.title, description: second.description });
  });

  it('offers no anonymous continuation when initialization was rejected, and gates unconfirmed Personal behind a manual choice', async () => {
    const { state, checkAccess, complete } = setup();
    checkAccess.mockResolvedValue(rejected);
    enterManual(state, endpointUrl);
    await state.checkAccess();
    expect(state.modes).toEqual(['static_bearer']);
    state.setOverride(true);
    expect(state.modes).toEqual(['personal', 'static_bearer']);
    state.selectMode('personal');
    state.setOverride(false);
    expect(state.selectedMode).toBeUndefined();
    expect(state.modes).toEqual(['static_bearer']);
    state.selectMode('none');
    expect(state.selectedMode).toBeUndefined();
    state.configure();
    expect(complete).not.toHaveBeenCalled();
    state.selectMode('static_bearer');
    expect(complete).not.toHaveBeenCalled();
    state.configure();
    expect(complete).toHaveBeenCalledWith('static_bearer', { endpointUrl, displayName: '', description: '' });
  });

  it('keeps a development loopback endpoint usable for shared setup without attempting a check', async () => {
    const { state, checkAccess, complete } = setup(true);
    enterManual(state, ' http://127.0.0.1:3001/mcp ');
    expect(state.canCheckManual).toBe(true);
    await state.checkAccess();
    expect(state.uncertainAccess).toBe(true);
    expect(checkAccess).not.toHaveBeenCalled();
    expect(state.modes).toEqual(['static_bearer']);
    state.setOverride(true);
    expect(state.modes).toEqual(['none', 'static_bearer']);
    state.finish('none');
    expect(complete).toHaveBeenCalledWith('none', { endpointUrl: 'http://127.0.0.1:3001/mcp', displayName: '', description: '' });
  });

  it.each(['http://mcp.example.com/mcp', 'https://admin:password@mcp.example.com/mcp', 'https://mcp.example.com/mcp#tag', 'https://mcp.example.com:0/mcp'])('rejects unsupported connector URL %s before checking', async (url): Promise<void> => {
    const { state, checkAccess } = setup();
    enterManual(state, url);
    expect(state.canCheckManual).toBe(false);
    await state.checkAccess();
    expect(checkAccess).not.toHaveBeenCalled();
  });

  it.each([
    { mode: 'personal', metadataUrl: endpointUrl, attaches: true },
    { mode: 'personal', metadataUrl: `${endpointUrl}/`, attaches: false },
    { mode: 'static_bearer', metadataUrl: endpointUrl, attaches: false }
  ] satisfies { mode: McpSetupMode; metadataUrl: string; attaches: boolean }[])('completes $mode with validated matching OAuth seed only when applicable ($attaches)', async ({ mode, metadataUrl, attaches }): Promise<void> => {
    const { state, checkAccess, complete } = setup();
    const metadata: EndpointDiscoveryResult = { kind: 'issuer_selection_required', endpoint_url: metadataUrl, issuer_urls: ['https://id1.example.com', 'https://id2.example.com'] };
    checkAccess.mockResolvedValue({ ...rejected, oauth: { kind: 'oauth_discovered', metadata } });
    enterManual(state, endpointUrl);
    await state.checkAccess();
    expect(state.modes).toContain('personal');
    state.finish(mode);
    const draft = { endpointUrl, displayName: '', description: '' };
    expect(complete).toHaveBeenCalledWith(mode, attaches ? { ...draft, oauthMetadata: metadata } : draft);
  });

  it('ignores a search superseded by input and a check abandoned by Back', async () => {
    const { state, search, checkAccess, accessLost } = setup();
    const pendingSearch = Promise.withResolvers<McpRegistryPage>();
    search.mockReturnValueOnce(pendingSearch.promise).mockResolvedValueOnce({ servers: [], next_cursor: '' });
    state.openSearch();
    state.changeTerm('old');
    const older = state.search();
    expect(state.searchStatus).toBe('loading');
    state.changeTerm('new');
    await state.search();
    pendingSearch.resolve({ servers: [registryServer('example/stale')], next_cursor: 'stale' });
    await older;
    expect(state.servers).toEqual([]);
    expect(state.searchStatus).toBe('ready');
    state.openManual();
    expect(state.step).toBe('search');
    state.back();
    const pendingCheck = Promise.withResolvers<McpEndpointAccessResult>();
    checkAccess.mockReturnValueOnce(pendingCheck.promise).mockResolvedValueOnce(inconclusive);
    enterManual(state, endpointUrl);
    const previous = state.checkAccess();
    expect(state.access?.kind).toBe('checking');
    state.back();
    state.changeManualUrl(`${endpointUrl}/new`);
    await state.checkAccess();
    pendingCheck.reject(new AuthenticationRequiredError());
    await previous;
    expect(state.anonymousResult).toBe('inconclusive');
    expect(state.endpointUrl).toBe(`${endpointUrl}/new`);
    expect(accessLost).not.toHaveBeenCalled();
  });

  it('fences access after disposal', async () => {
    const { state, checkAccess, accessLost, complete } = setup();
    const pending = Promise.withResolvers<McpEndpointAccessResult>();
    checkAccess.mockReturnValue(pending.promise);
    enterManual(state, endpointUrl);
    const check = state.checkAccess();
    state.dispose();
    pending.resolve(anonymous);
    await check;
    state.finish('none');
    expect(state.modes).toEqual([]);
    expect(complete).not.toHaveBeenCalled();
    expect(accessLost).not.toHaveBeenCalled();
  });

  it.each([new AuthenticationRequiredError(), new HttpError(403, 'Forbidden', {})])('fences changes and notifies the parent on active administration access loss: %s', async (error): Promise<void> => {
    const { state, search, checkAccess, complete, accessLost } = setup();
    search.mockRejectedValue(error);
    state.openSearch();
    state.changeTerm('example');
    await state.search();
    expect(accessLost).toHaveBeenCalledOnce();
    enterManual(state, endpointUrl);
    await state.checkAccess();
    state.finish('static_bearer');
    expect(checkAccess).not.toHaveBeenCalled();
    expect(complete).not.toHaveBeenCalled();
  });
});
