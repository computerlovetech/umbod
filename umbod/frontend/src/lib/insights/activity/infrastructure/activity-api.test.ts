import { describe, expect, test, vi } from 'vitest';
import { InMemoryPublicConfigurationProvider } from '#lib/admin/infrastructure/public-configuration.js';
import { AuthenticationRequiredError, HttpError, SchemaValidationError, browserTransport, type Transport, type TransportRequest } from '#lib/admin/infrastructure/transport.js';
import { usageSummaryFixture } from '#lib/dashboard/usage-fixtures.test-support.js';
import { createActivityApi } from './activity-api';

const period = {
  days: 7,
  as_of: '2026-11-09T12:00:00Z',
  window: { start: '2026-11-03T00:00:00Z', end: '2026-11-10T00:00:00Z' }
} as const;
const identity_key = 'account-one';
const unavailable = { status: 'unavailable' } as const;
const outcomes = { success: 2, failure: 1, unknown: 3 };
const rankedTool = { tool_name: 'Search', count: 1 };
const harness = { status: 'available', summary: { outcomes, top_tools: [rankedTool], skill_activations: 4 } } as const;
const key = { source: 'claude-code-desktop', session_id: ' logs/sub?#%é ' } as const;
const session = { key, first_seen_at: '2026-11-04T09:10:00+00:00', last_seen_at: '2026-11-05T10:22:33.123456Z', outcomes };
const sessionReport = { identity_key, session, top_tools: [rankedTool], failed_tools: [rankedTool], has_more_failed_tools: false, skill_activations: 5 };
const sessionPage = { identity_key, period, sessions: [session], page: { kind: 'more', cursor: 'opaque+%/=?' } };
const fullOutage = { identity_key, period, harness: unavailable, mcp: unavailable };

function setup(request: typeof fetch): ReturnType<typeof createActivityApi> {
  return createActivityApi(browserTransport({
    fetch: request,
    configuration: new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: 'https://mcp.example.test' })
  }));
}

function respond(body: unknown, status = 200): ReturnType<typeof vi.fn<typeof fetch>> {
  return vi.fn<typeof fetch>().mockResolvedValue(Response.json(body, { status }));
}

function withoutIdentity<T extends { identity_key: string }>(value: T): Omit<T, 'identity_key'> {
  const { identity_key: _identityKey, ...summary } = value;
  return summary;
}

describe('activity API transport', () => {
  test('uses the injected transport for all three bodyless reads', async (): Promise<void> => {
    const responses = [{ ...fullOutage, harness }, sessionPage, sessionReport];
    const requests: TransportRequest<unknown>[] = [];
    const transport: Transport = {
      request: async <T>(request: TransportRequest<T>): Promise<T> => {
        requests.push(request);
        if (!request.outputSchema) throw new Error('Expected an output schema');
        return request.outputSchema.parse(responses.shift());
      }
    };
    const activity = createActivityApi(transport);

    await expect(activity.overview(7)).resolves.toEqual({ ...fullOutage, harness });
    await expect(activity.sessions({})).resolves.toEqual(sessionPage);
    await expect(activity.session(key)).resolves.toEqual(sessionReport);
    expect(requests.map(({ method, body, requestBody }) => ({ method, body, requestBody }))).toEqual(
      Array.from({ length: 3 }, () => ({ method: 'GET', body: undefined, requestBody: undefined }))
    );
  });

  test('returns separate available harness and MCP summaries', async (): Promise<void> => {
    const overview = { identity_key, period, harness, mcp: { status: 'available', summary: usageSummaryFixture() } };
    const request = respond(overview);
    const { signal } = new AbortController();

    await expect(setup(request).overview(7, signal)).resolves.toEqual(overview);
    expect(request).toHaveBeenCalledWith('/api/me/activity?days=7', expect.objectContaining({ method: 'GET', signal }));
  });

  test('preserves a partial outage and accepts a typed overview on HTTP 503', async (): Promise<void> => {
    const partialOutage = { identity_key, period, harness, mcp: unavailable };

    await expect(setup(respond(partialOutage)).overview(7)).resolves.toEqual(partialOutage);
    await expect(setup(respond(fullOutage, 503)).overview(7)).resolves.toEqual(fullOutage);
  });

  test.each([{ detail: 'Service unavailable' }, { ...fullOutage, harness }])('preserves HTTP 503 when the body is not a full outage overview', async (body): Promise<void> => {
    const error = await setup(respond(body, 503)).overview(30).catch((failure: unknown): unknown => failure);

    expect(error).toBeInstanceOf(HttpError);
    expect(error).toMatchObject({ status: 503, body });
  });

  test('encodes literal search and opaque cursor query parameters with cancellation', async (): Promise<void> => {
    const request = respond(sessionPage);
    const { signal } = new AbortController();

    await expect(setup(request).sessions({ days: 7, q: ' /+%_&?é ', cursor: sessionPage.page.cursor, limit: 1 }, signal)).resolves.toEqual(sessionPage);
    expect(request).toHaveBeenCalledWith('/api/me/activity/sessions?days=7&q=+%2F%2B%25_%26%3F%C3%A9+&cursor=opaque%2B%25%2F%3D%3F&limit=1', expect.objectContaining({ method: 'GET', signal }));
  });

  test('omits omitted query arguments rather than encoding undefined values', async (): Promise<void> => {
    const end = { identity_key, period, sessions: [], page: { kind: 'end' } };
    const request = respond(end);

    await expect(setup(request).sessions({})).resolves.toEqual(end);
    expect(request).toHaveBeenCalledWith('/api/me/activity/sessions', expect.objectContaining({ method: 'GET' }));
  });

  test('encodes a session ID as one URL segment and validates session details', async (): Promise<void> => {
    const request = respond(sessionReport);
    const { signal } = new AbortController();

    await expect(setup(request).session(key, signal)).resolves.toEqual(sessionReport);
    expect(request).toHaveBeenCalledWith('/api/me/activity/sessions/claude-code-desktop/%20logs%2Fsub%3F%23%25%C3%A9%20', expect.objectContaining({ method: 'GET', signal }));
  });

  test('supports 1,024 Unicode code points in a session ID', async (): Promise<void> => {
    const unicodeKey = { ...key, session_id: '🎧'.repeat(1024) };
    const report = { ...sessionReport, session: { ...session, key: unicodeKey } };

    await expect(setup(respond(report)).session(unicodeKey)).resolves.toEqual(report);
  });

  test.each(['.', '..', '\u0000', ' \t ', 'a'.repeat(1025), '\ud800'])('rejects invalid session IDs before network access: %j', async (session_id): Promise<void> => {
    const request = vi.fn<typeof fetch>();

    await expect(setup(request).session({ ...key, session_id })).rejects.toMatchObject({ name: 'SchemaValidationError', direction: 'outbound' });
    expect(request).not.toHaveBeenCalled();
  });

  test.each([{ limit: 101 }, { cursor: '' }, { q: 'x'.repeat(129) }])('rejects invalid sessions query arguments before network access: %j', async (query): Promise<void> => {
    const request = vi.fn<typeof fetch>();

    await expect(setup(request).sessions(query)).rejects.toMatchObject({ name: 'SchemaValidationError', direction: 'outbound' });
    expect(request).not.toHaveBeenCalled();
  });

  test('rejects malformed inbound payloads for each route', async (): Promise<void> => {
    const overview = { identity_key, period, harness, mcp: { status: 'available', summary: { ...usageSummaryFixture(), identity_key } } };
    const missingCursor = { ...sessionPage, page: { kind: 'more' } };
    const invalidOutcomes = { ...sessionReport, session: { ...session, outcomes: { ...outcomes, unknown: -1 } } };

    await expect(setup(respond(overview)).overview(7)).rejects.toBeInstanceOf(SchemaValidationError);
    await expect(setup(respond(missingCursor)).sessions({})).rejects.toMatchObject({ direction: 'inbound' });
    await expect(setup(respond(invalidOutcomes)).session(key)).rejects.toMatchObject({ direction: 'inbound' });
  });

  test('rejects a response for a different requested period', async (): Promise<void> => {
    const overview = { ...fullOutage, harness };
    const issue = { direction: 'inbound', issues: [expect.objectContaining({ path: ['period', 'days'] })] };

    await expect(setup(respond(overview)).overview(30)).rejects.toMatchObject(issue);
    await expect(setup(respond(fullOutage, 503)).overview(30)).rejects.toMatchObject(issue);
    await expect(setup(respond(sessionPage)).sessions({ days: 30 })).rejects.toMatchObject(issue);
  });

  test.each([
    { source: 'codex', session_id: key.session_id },
    { ...key, session_id: 'another-session' }
  ] as const)('rejects a report for a different session key %j', async (requestedKey): Promise<void> => {
    await expect(setup(respond(sessionReport)).session(requestedKey)).rejects.toMatchObject({
      direction: 'inbound', issues: [expect.objectContaining({ path: ['session', 'key'] })]
    });
  });

  test('rejects duplicate composite session keys but allows the same ID from different sources', async (): Promise<void> => {
    const duplicate = { ...sessionPage, sessions: [session, { ...session, outcomes: { success: 1, failure: 0, unknown: 0 } }] };
    const distinct = { ...sessionPage, sessions: [session, { ...session, key: { ...key, source: 'codex' } }] };

    await expect(setup(respond(duplicate)).sessions({})).rejects.toMatchObject({
      direction: 'inbound', issues: [expect.objectContaining({ path: ['sessions'] })]
    });
    await expect(setup(respond(distinct)).sessions({})).resolves.toEqual(distinct);
  });

  test('requires the MCP usage summary to match Activity dates and the as_of instant', async (): Promise<void> => {
    const summary = usageSummaryFixture();
    const overview = { ...fullOutage, harness, mcp: { status: 'available', summary } };
    const shiftedRange = { ...overview, mcp: { ...overview.mcp, summary: usageSummaryFixture(30) } };
    const shiftedAsOf = { ...overview, mcp: { ...overview.mcp, summary: { ...summary, as_of: '2026-11-09T12:00:00.000001Z' } } };
    const equivalentAsOf = { ...overview, mcp: { ...overview.mcp, summary: { ...summary, as_of: '2026-11-09T12:00:00.000000+00:00' } } };

    await expect(setup(respond(shiftedRange)).overview(7)).rejects.toMatchObject({ direction: 'inbound' });
    await expect(setup(respond(shiftedAsOf)).overview(7)).rejects.toMatchObject({ direction: 'inbound' });
    await expect(setup(respond(equivalentAsOf)).overview(7)).resolves.toEqual(equivalentAsOf);
  });

  test('requires an account identity on every Activity response', async (): Promise<void> => {
    const overview = withoutIdentity({ ...fullOutage, harness });

    await expect(setup(respond(overview)).overview(7)).rejects.toMatchObject({ direction: 'inbound' });
    await expect(setup(respond(withoutIdentity(fullOutage), 503)).overview(7)).rejects.toMatchObject({ status: 503 });
    await expect(setup(respond(withoutIdentity(sessionPage))).sessions({})).rejects.toMatchObject({ direction: 'inbound' });
    await expect(setup(respond(withoutIdentity(sessionReport))).session(key)).rejects.toMatchObject({ direction: 'inbound' });
  });

  test('preserves transport failures on authenticated routes', async (): Promise<void> => {
    await expect(setup(respond({}, 401)).overview(7)).rejects.toBeInstanceOf(AuthenticationRequiredError);
    await expect(setup(respond({}, 422)).sessions({ cursor: 'mismatched' })).rejects.toMatchObject({ status: 422 });
    await expect(setup(respond(fullOutage, 503)).sessions({})).rejects.toMatchObject({ status: 503 });
    await expect(setup(respond({}, 404)).session(key)).rejects.toMatchObject({ status: 404 });
    await expect(setup(respond(fullOutage, 503)).session(key)).rejects.toMatchObject({ status: 503 });
  });
});
