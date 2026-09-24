import { describe, expect, test } from 'vitest';

import { createHeaderAccountUserInfoBoundary } from '../header/accountIdentity';

type CurrentUserIdentity = {
  id: string;
  email: string;
  name: string;
  picture?: string | null;
};

type HeaderAccountIdentityState =
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

interface HeaderAccountUserInfoBoundary {
  viewHeaderAccountIdentity(currentUser: CurrentUserIdentity | null): HeaderAccountIdentityState;
}

function createBoundary(): HeaderAccountUserInfoBoundary {
  return createHeaderAccountUserInfoBoundary();
}

describe('header account user info acceptance', () => {
  test('authenticated user sees their account identity in the header', () => {
    const boundary = createBoundary();

    const headerIdentity = boundary.viewHeaderAccountIdentity({
      id: 'user-123',
      email: 'alex@example.com',
      name: 'Alex Morgan'
    });

    expect(headerIdentity).toEqual({
      kind: 'visible',
      name: 'Alex Morgan',
      email: 'alex@example.com',
      picture: null,
      hiddenValues: {
        id: 'user-123'
      }
    });
  });

  test('user with unknown name sees unknown and email in the header', () => {
    const boundary = createBoundary();

    const headerIdentity = boundary.viewHeaderAccountIdentity({
      id: 'user-123',
      email: 'alex@example.com',
      name: 'unknown'
    });

    expect(headerIdentity).toEqual({
      kind: 'visible',
      name: 'unknown',
      email: 'alex@example.com',
      picture: null,
      hiddenValues: {
        id: 'user-123'
      }
    });
  });

  test('unauthorized user identity hides the account identity area', () => {
    const boundary = createBoundary();

    const headerIdentity = boundary.viewHeaderAccountIdentity(null);

    expect(headerIdentity).toEqual({ kind: 'hidden' });
  });

  test('unavailable user identity hides the account identity area', () => {
    const boundary = createBoundary();

    const headerIdentity = boundary.viewHeaderAccountIdentity(null);

    expect(headerIdentity).toEqual({ kind: 'hidden' });
  });

  test('non-admin authenticated user sees their own account identity', () => {
    const boundary = createBoundary();

    const headerIdentity = boundary.viewHeaderAccountIdentity({
      id: 'user-123',
      email: 'alex@example.com',
      name: 'Alex Morgan'
    });

    expect(headerIdentity).toEqual({
      kind: 'visible',
      name: 'Alex Morgan',
      email: 'alex@example.com',
      picture: null,
      hiddenValues: {
        id: 'user-123'
      }
    });
  });

  test('header displays the standard user picture claim', () => {
    const boundary = createBoundary();

    const headerIdentity = boundary.viewHeaderAccountIdentity({
      id: 'user-123',
      email: 'alex@example.com',
      name: 'Alex Morgan',
      picture: 'https://example.com/alex.png'
    });

    expect(headerIdentity).toEqual({
      kind: 'visible',
      name: 'Alex Morgan',
      email: 'alex@example.com',
      picture: 'https://example.com/alex.png',
      hiddenValues: {
        id: 'user-123'
      }
    });
  });

  test('header displays only the current user minimal identity', () => {
    const boundary = createBoundary();

    const headerIdentity = boundary.viewHeaderAccountIdentity({
      id: 'jwt-user-123',
      email: 'jwt-alex@example.com',
      name: 'JWT Alex'
    });

    expect(headerIdentity).toEqual({
      kind: 'visible',
      name: 'JWT Alex',
      email: 'jwt-alex@example.com',
      picture: null,
      hiddenValues: {
        id: 'jwt-user-123'
      }
    });
    expect(JSON.stringify(headerIdentity)).not.toContain('avatar');
    expect(JSON.stringify(headerIdentity)).not.toContain('roles');
    expect(JSON.stringify(headerIdentity)).not.toContain('groups');
    expect(JSON.stringify(headerIdentity)).not.toContain('created_at');
    expect(JSON.stringify(headerIdentity)).not.toContain('last_login_at');
  });

  test('header identity updates to match loaded current user', () => {
    const boundary = createBoundary();

    const previousIdentity = boundary.viewHeaderAccountIdentity({
      id: 'user-123',
      email: 'alex@example.com',
      name: 'Alex Morgan'
    });
    const latestIdentity = boundary.viewHeaderAccountIdentity({
      id: 'user-456',
      email: 'sam@example.com',
      name: 'Sam Rivera'
    });

    expect(previousIdentity).toEqual({
      kind: 'visible',
      name: 'Alex Morgan',
      email: 'alex@example.com',
      picture: null,
      hiddenValues: {
        id: 'user-123'
      }
    });
    expect(latestIdentity).toEqual({
      kind: 'visible',
      name: 'Sam Rivera',
      email: 'sam@example.com',
      picture: null,
      hiddenValues: {
        id: 'user-456'
      }
    });
  });
});
