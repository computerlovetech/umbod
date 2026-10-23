import {
  createHeaderAccountUserInfoBoundary,
  type CurrentUserIdentity,
  type HeaderAccountIdentityState
} from '$lib/header/accountIdentity';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';

export interface CurrentUserApi {
  currentUser(): Promise<CurrentUserIdentity>;
}

export type AdminAccess = 'allowed' | 'denied' | 'sign-in' | 'unavailable';

export interface WorkspaceAccess {
  adminAccess: AdminAccess;
  accountIdentity: HeaderAccountIdentityState;
}

export async function resolveWorkspaceAccess(api: CurrentUserApi): Promise<WorkspaceAccess> {
  try {
    const user = await api.currentUser();
    return {
      adminAccess: 'allowed',
      accountIdentity: createHeaderAccountUserInfoBoundary().viewHeaderAccountIdentity(user)
    };
  } catch (cause) {
    if (cause instanceof AuthenticationRequiredError || (cause instanceof HttpError && cause.status === 401)) {
      return { adminAccess: 'sign-in', accountIdentity: { kind: 'hidden' } };
    }
    return {
      adminAccess: cause instanceof HttpError && cause.status === 403 ? 'denied' : 'unavailable',
      accountIdentity: { kind: 'hidden' }
    };
  }
}
