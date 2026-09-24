import type { CurrentUserIdentity } from '$lib/header/accountIdentity';

declare global {
  namespace App {
    interface Locals {
      currentUser: CurrentUserIdentity | null;
    }
  }
}

export {};
