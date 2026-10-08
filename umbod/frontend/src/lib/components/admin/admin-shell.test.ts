import { render } from 'svelte/server';
import { createRawSnippet } from 'svelte';
import { describe, expect, test, vi } from 'vitest';
import AdminShell from './AdminShell.svelte';

vi.mock('$app/state', () => ({ navigating: { to: null, from: null } }));

describe('admin shell logout', () => {
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
