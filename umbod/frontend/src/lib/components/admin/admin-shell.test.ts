import { render } from 'svelte/server';
import { createRawSnippet } from 'svelte';
import { describe, expect, test, vi } from 'vitest';
import AdminShell from './AdminShell.svelte';
import AppHeader from '../header/AppHeader.svelte';
import { currentUserIdentitySchema, createHeaderAccountUserInfoBoundary } from '../../header/accountIdentity';

vi.mock('$app/state', () => ({ navigating: { to: null, from: null } }));

describe('admin shell logout', () => {
  test('nullable email hides only its row in both account presentations', () => {
    const profile = currentUserIdentitySchema.parse({
      id: 'admin-id', email: null, name: 'unknown', picture: 'https://example.com/admin.png'
    });
    const accountIdentity = createHeaderAccountUserInfoBoundary().viewHeaderAccountIdentity(profile);
    const logout = vi.fn<() => Promise<void>>().mockResolvedValue();
    const header = render(AppHeader, { props: { accountIdentity } });
    const shell = render(AdminShell, { props: {
      activeItem: 'overview', accountIdentity, logout: { logout },
      children: createRawSnippet(() => ({ render: (): string => '<p>Content</p>' }))
    } });
    for (const { body } of [header, shell]) {
      expect(body).toContain('unknown');
      expect(body).toContain('https://example.com/admin.png');
      expect(body).not.toContain('class="account-email');
      expect(body).not.toContain('admin-id');
    }
    expect(shell.body).toContain('Log out</button>');
    expect(logout).not.toHaveBeenCalled();
  });

  test('current-user contract requires explicit nullable email', () => {
    expect(currentUserIdentitySchema.safeParse({ id: 'admin-id', name: 'unknown' }).success).toBe(false);
    expect(currentUserIdentitySchema.safeParse({ id: 'admin-id', name: 'unknown', email: 123 }).success).toBe(false);
  });

  test.each(['visible', 'hidden'] as const)('offers an explicit logout independent of %s identity without automatic navigation', (kind) => {
    const logout = vi.fn<() => Promise<void>>().mockResolvedValue();
    const { body } = render(AdminShell, { props: {
      activeItem: 'overview',
      accountIdentity: kind === 'visible' ? { kind, name: 'Administrator', email: 'admin@example.test', picture: null, hiddenValues: { id: 'admin-id' } } : { kind },
      children: createRawSnippet(() => ({ render: (): string => '<p>Content</p>' })),
      logout: { logout }
    } });
    expect(body).toContain('type="button"');
    expect(body).toContain('Log out</button>');
    expect(logout).not.toHaveBeenCalled();
  });
});
