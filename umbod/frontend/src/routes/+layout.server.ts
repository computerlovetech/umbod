import { createHeaderAccountUserInfoBoundary, type HeaderAccountIdentityState } from '$lib/header/accountIdentity';
import type { LayoutServerLoad } from './$types';

export type AppLayoutData = {
  accountIdentity: HeaderAccountIdentityState;
};

export const load: LayoutServerLoad = ({ locals }): AppLayoutData => {
  const boundary = createHeaderAccountUserInfoBoundary();
  return { accountIdentity: boundary.viewHeaderAccountIdentity(locals.currentUser) };
};
