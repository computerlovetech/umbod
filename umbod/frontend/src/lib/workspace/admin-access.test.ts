import { describe, expect, test } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { currentUserIdentitySchema, type CurrentUserIdentity } from '$lib/header/accountIdentity';
import { resolveWorkspaceAccess, type CurrentUserApi } from './admin-access';

const user = currentUserIdentitySchema.parse({ id: 'admin-id', name: 'Alex', email: null });

class InMemoryCurrentUserApi implements CurrentUserApi {
  constructor(private readonly outcome: CurrentUserIdentity | Error) {}

  async currentUser(): Promise<CurrentUserIdentity> {
    if (this.outcome instanceof Error) throw this.outcome;
    return this.outcome;
  }
}

describe('workspace access presentation', () => {
  test('validated current user permits administration and preserves identity', async (): Promise<void> => {
    const api: CurrentUserApi = new InMemoryCurrentUserApi(user);
    await expect(resolveWorkspaceAccess(api)).resolves.toEqual({
      adminAccess: 'allowed',
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
    const api: CurrentUserApi = new InMemoryCurrentUserApi(cause);
    await expect(resolveWorkspaceAccess(api)).resolves.toEqual({ adminAccess, accountIdentity: { kind: 'hidden' } });
  });
});
