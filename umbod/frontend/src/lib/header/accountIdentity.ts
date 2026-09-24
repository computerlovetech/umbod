import { z } from 'zod';

export const currentUserIdentitySchema = z.object({
  id: z.string(),
  email: z.string(),
  name: z.string(),
  picture: z.string().nullish()
});

export type CurrentUserIdentity = z.infer<typeof currentUserIdentitySchema>;

export type HeaderAccountIdentityState =
  | {
      kind: 'visible';
      name: string;
      email: string;
      picture: string | null;
      hiddenValues: {
        id: string;
      };
    }
  | {
      kind: 'hidden';
    };

export interface HeaderAccountUserInfoBoundary {
  viewHeaderAccountIdentity(currentUser: CurrentUserIdentity | null): HeaderAccountIdentityState;
}

export function createHeaderAccountUserInfoBoundary(): HeaderAccountUserInfoBoundary {
  return {
    viewHeaderAccountIdentity(currentUser: CurrentUserIdentity | null): HeaderAccountIdentityState {
      if (currentUser === null) {
        return { kind: 'hidden' };
      }

      return {
        kind: 'visible',
        name: currentUser.name,
        email: currentUser.email,
        picture: currentUser.picture ?? null,
        hiddenValues: {
          id: currentUser.id
        }
      };
    }
  };
}
