import { describe, expect, test } from 'vitest';
import { administrationNavigation, workspaceNavigation } from './navigation';

describe('contextual workspace navigation', (): void => {
  test('ordinary workspace links carry the preview icons without exposing administration', (): void => {
    const links = workspaceNavigation(false);
    expect(links.map((link): string => link.id)).toEqual(['dashboard', 'connectors', 'files', 'gettingStarted']);
    expect(links.map((link): string | undefined => link.icon)).toEqual(['dashboard', 'connectors', 'files', 'gettingStarted']);
    expect(links.map((link): string => link.href)).toEqual(['/dashboard', '/connectors', '/files', '/getting-started']);
    expect(links.some((link): boolean => link.href.startsWith('/admin'))).toBe(false);
  });

  test('authorized workspace adds one divided Administration entry', (): void => {
    const links = workspaceNavigation(true);
    expect(links).toHaveLength(5);
    expect(links[4]).toEqual({
      id: 'administration', label: 'Administration', href: '/admin/connectors',
      icon: 'administration', startsSection: true
    });
  });

  test('administration sidebar preserves page destinations in preview order without workspace links', (): void => {
    expect(administrationNavigation.map((link): string => link.href)).toEqual([
      '/admin/connectors', '/admin/groups', '/admin/group-permissions/connectors',
      '/admin/analytics', '/admin/instance-configuration'
    ]);
    expect(administrationNavigation.map((link): string | undefined => link.icon)).toEqual([
      'connectors', 'groups', 'permissions', 'analytics', 'settings'
    ]);
  });
});
