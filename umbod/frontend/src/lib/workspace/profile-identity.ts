import { createHeaderAccountUserInfoBoundary, type HeaderAccountIdentityState } from '$lib/header/accountIdentity';
import type { WorkspaceProfile } from './domain/profile';

export function workspaceAccountIdentity(profile: WorkspaceProfile): HeaderAccountIdentityState {
  return createHeaderAccountUserInfoBoundary().viewHeaderAccountIdentity({ ...profile.user, id: profile.identity_key });
}
