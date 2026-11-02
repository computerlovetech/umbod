import {
  createHeaderAccountUserInfoBoundary,
  type HeaderAccountIdentityState
} from '$lib/header/accountIdentity';
import type { WorkspaceApi } from './api';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';

export type AdminAccess = 'allowed' | 'denied' | 'sign-in' | 'unavailable';

export interface WorkspaceAccess {
  adminAccess: AdminAccess;
  accountIdentity: HeaderAccountIdentityState;
}

export async function resolveWorkspaceAccess(api: WorkspaceApi): Promise<WorkspaceAccess> {
  try {
    const profile = await api.profile.get();
    return {
      adminAccess: profile.capabilities.administration ? 'allowed' : 'denied',
      accountIdentity: createHeaderAccountUserInfoBoundary().viewHeaderAccountIdentity(profile.user)
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
