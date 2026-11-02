import { describe, expect, test } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { workspaceProfileSchema } from './domain/profile';
import { InMemoryWorkspaceApi } from './in-memory-api.test-support';
import { resolveWorkspaceAccess } from './admin-access';
import type { WorkspaceApi } from './api';

const user = { id: 'admin-id', name: 'Alex', email: null, picture: null };

describe('workspace access presentation', () => {
  test.each([true, false])('administration capability %s controls navigation without hiding identity', async (administration): Promise<void> => {
    const api: WorkspaceApi = new InMemoryWorkspaceApi(workspaceProfileSchema.parse({ user, capabilities: { administration } }));
    await expect(resolveWorkspaceAccess(api)).resolves.toEqual({
      adminAccess: administration ? 'allowed' : 'denied',
      accountIdentity: { kind: 'visible', name: 'Alex', email: null, picture: null, hiddenValues: { id: 'admin-id' } }
    });
  });

  test.each([
    [new AuthenticationRequiredError(), 'sign-in'],
    [new HttpError(401, 'Unauthorized', null), 'sign-in'],
    [new HttpError(403, 'Forbidden', null), 'denied'],
    [new HttpError(500, 'Internal Server Error', null), 'unavailable'],
    [new SchemaValidationError('inbound', []), 'unavailable'],
    [new NetworkError(new Error('offline')), 'unavailable']
  ] as const)('fails closed for %s as %s without throwing', async (cause, adminAccess): Promise<void> => {
    const api: WorkspaceApi = new InMemoryWorkspaceApi(cause);
    await expect(resolveWorkspaceAccess(api)).resolves.toEqual({ adminAccess, accountIdentity: { kind: 'hidden' } });
  });
});
