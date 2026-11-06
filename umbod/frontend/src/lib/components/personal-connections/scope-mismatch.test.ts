// Acceptance coverage for issue #37: explain personal OAuth scope configuration failures.
import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import { HttpError } from '$lib/admin/infrastructure/transport';
import type { PersonalConnectionsApi } from '$lib/personal-connections/api';
import { InMemoryAttemptScheduler } from '$lib/personal-connections/infrastructure/in-memory-attempt-scheduler';
import { InMemoryPersonalConnectionsApi } from '$lib/personal-connections/infrastructure/in-memory-api';
import { ConnectionState } from '$lib/personal-connections/state/connection-state.svelte';
import { authorizationHealth, selection } from '$lib/personal-connections/test-fixtures';
import ConnectionCard from './ConnectionCard.svelte';

const sentinels = ['sentinel-access-token', 'sentinel-authorization-code', 'sentinel-client-secret', 'sentinel-raw-response-body'];

async function startWithUnconfiguredProviderDefault(connector: string, scope: string): Promise<ConnectionState> {
  const named = { ...selection, display_name: connector };
  const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([named], { [named.connector_id]: authorizationHealth });
  const state = new ConnectionState(named, api, vi.fn(), undefined, undefined, new InMemoryAttemptScheduler());
  vi.spyOn(api.authorization, 'start').mockRejectedValue(new HttpError(422, `https://private.test?code=${sentinels[1]}`, {
    detail: {
      code: 'personal_oauth_scope_mismatch', step: 'registration', configured_scopes: [], returned_scopes: [scope],
      access_token: sentinels[0], client_secret: sentinels[2], body: sentinels[3]
    }
  }));
  await state.start();
  return state;
}

describe('personal OAuth scope configuration failures', () => {
  test.each([
    { connector: 'Document service', scope: 'documents.read' },
    { connector: 'Task service', scope: 'tasks:read' }
  ])('an administrator is told $connector returned $scope and where to fix it', async ({ connector, scope }): Promise<void> => {
    const state = await startWithUnconfiguredProviderDefault(connector, scope);
    const manageHref = `/admin/downstream-mcp-connectors?connector=${selection.connector_id}`;

    const body = render(ConnectionCard, { props: { state, embedded: true, manageHref } }).body;

    expect(body).toContain(`“${connector}” returned scope “${scope}” during client registration, but no scopes were configured in Umbod.`);
    expect(body).toContain('Requested scopes setting');
    expect(body).toContain(`href="${manageHref}#personal-policy-${selection.connector_id}-scopes"`);
    for (const sentinel of sentinels) expect(body).not.toContain(sentinel);
    expect(state.attempt).toBeNull();
  });

  test('an ordinary user is told to ask an administrator to update the scope settings', async (): Promise<void> => {
    const state = await startWithUnconfiguredProviderDefault('Document service', 'documents.read');

    const body = render(ConnectionCard, { props: { state, embedded: true } }).body;

    expect(body).toContain('scope settings prevent sign-in');
    expect(body).toContain('Ask an administrator to update its Requested scopes setting.');
    expect(body).not.toContain('documents.read');
    expect(body).not.toContain('/admin/');
    for (const sentinel of sentinels) expect(body).not.toContain(sentinel);
    expect(state.attempt).toBeNull();
  });
});
