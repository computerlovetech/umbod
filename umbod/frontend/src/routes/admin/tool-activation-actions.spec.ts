import type { RequestEvent } from '@sveltejs/kit';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { HttpError } from '$lib/admin/infrastructure/transport';

const serverApiState = vi.hoisted(() => ({ current: undefined as unknown }));

vi.mock('$lib/admin/infrastructure/server-api', () => ({
  adminServerApi: () => serverApiState.current
}));

import { actions as nativeActions } from './connectors/+page.server';
import { actions as downstreamActions } from './downstream-mcp-connectors/+page.server';
import { actions as openApiActions } from './openapi-connectors/+page.server';

type SaveAction = (event: never) => unknown;

type ActivationRoute = {
  saveActivations: ReturnType<typeof vi.fn>;
  listActivations: ReturnType<typeof vi.fn>;
};

const conflictBody = {
  code: 'invocation_policy_revision_conflict',
  conflicts: [{ tool_id: 'search', expected_revision: 1, current_mode: 'ask', current_revision: 2 }]
};

function eventFor(kind: 'native' | 'openapi' | 'downstream'): RequestEvent {
  const form = new FormData();
  form.set('connectorId', 'connector-1');
  form.set('toolActivations', kind === 'native' ? '[]' : JSON.stringify({ tools: [] }));
  form.set('invocationPolicies', JSON.stringify({ tools: [{ tool_id: 'search', mode: 'direct', expected_revision: 1 }] }));
  return { request: new Request('http://localhost/action', { method: 'POST', body: form }) } as RequestEvent;
}

function routeRejecting(saveError: unknown): ActivationRoute {
  return {
    saveActivations: vi.fn().mockRejectedValue(saveError),
    listActivations: vi.fn().mockRejectedValue(new HttpError(503, 'Unavailable', undefined))
  };
}

async function invoke(action: SaveAction, kind: 'native' | 'openapi' | 'downstream'): Promise<unknown> {
  return action(eventFor(kind) as never);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('saveToolActivations action reconciliation wiring', () => {
  test.each([
    ['native', nativeActions.saveToolActivations],
    ['openapi', openApiActions.saveToolActivations],
    ['downstream', downstreamActions.saveToolActivations]
  ] as const)('%s retains its conflict response when authoritative loading fails', async (kind, action) => {
    const route = routeRejecting(new HttpError(409, 'Conflict', conflictBody));
    serverApiState.current = kind === 'native'
      ? { connectors: { tools: route } }
      : kind === 'openapi'
        ? { openApiConnectors: { connectors: route } }
        : { downstreamMcpConnectors: route };

    const result = await invoke(action as SaveAction, kind);

    expect(result).toMatchObject({
      status: 409,
      data: {
        status: 'conflict',
        connectorId: 'connector-1',
        message: 'Invocation policies changed by another administrator.',
        policyConflicts: conflictBody.conflicts
      }
    });
    expect(result).not.toHaveProperty('data.authoritativeActivationResponse');
    expect(result).not.toHaveProperty('data.authoritativePolicyResponse');
    expect(route.listActivations).toHaveBeenCalledWith('connector-1');
  });

  test('native maps an operational save failure to 503 when authoritative loading also fails', async () => {
    const route = routeRejecting(new HttpError(500, 'Internal Server Error', undefined));
    serverApiState.current = { connectors: { tools: route } };

    await expect(invoke(nativeActions.saveToolActivations as SaveAction, 'native')).resolves.toMatchObject({
      status: 503,
      data: { status: 'failed', connectorId: 'connector-1', errorMessage: 'Tool changes could not be saved.' }
    });
  });

  test('downstream preserves presentActionFailure mapping when authoritative loading also fails', async () => {
    const saveError = new HttpError(404, 'Not Found', {
      detail: { code: 'tool_not_found', message: 'missing', phase: 'connector', retryable: false, context: {} }
    });
    const route = routeRejecting(saveError);
    serverApiState.current = { downstreamMcpConnectors: route };

    await expect(invoke(downstreamActions.saveToolActivations as SaveAction, 'downstream')).resolves.toMatchObject({
      status: 404,
      data: {
        status: 'invalid',
        connectorId: 'connector-1',
        message: 'This downstream tool no longer exists. Refresh discovery and try again.'
      }
    });
  });
});
