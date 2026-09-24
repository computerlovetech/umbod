import { createHeaderAccountUserInfoBoundary, type HeaderAccountIdentityState } from '$lib/header/accountIdentity';
import type { LayoutServerLoad } from './$types';

export type AdminLayoutData = {
  accountIdentity: HeaderAccountIdentityState;
};

export const load: LayoutServerLoad = ({ locals }): AdminLayoutData => {
  const boundary = createHeaderAccountUserInfoBoundary();
  return { accountIdentity: boundary.viewHeaderAccountIdentity(locals.currentUser) };
};
