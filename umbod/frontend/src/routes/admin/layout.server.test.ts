import { describe, expect, test } from 'vitest';
import type { LayoutServerLoad } from './$types';
import { load } from './+layout.server';

function loadEvent(currentUser: App.Locals['currentUser']): Parameters<LayoutServerLoad>[0] {
  return { locals: { currentUser } } as Parameters<LayoutServerLoad>[0];
}

describe('admin layout account identity', () => {
  test('loads account identity when entering the admin route through client navigation', async () => {
    const data = await load(
      loadEvent({
        id: 'user-123',
        email: 'alex@example.com',
        name: 'Alex Morgan',
        picture: null
      })
    );

    expect(data).toEqual({
      accountIdentity: {
        kind: 'visible',
        name: 'Alex Morgan',
        email: 'alex@example.com',
        picture: null,
        hiddenValues: { id: 'user-123' }
      }
    });
  });
});
