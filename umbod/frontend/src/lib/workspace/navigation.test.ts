import { describe, expect, test } from 'vitest';
import { administrationNavigation, workspaceAccountLinks, workspaceNavigation } from './navigation';

describe('contextual workspace navigation', (): void => {
  test('ordinary workspace links carry the preview icons without exposing administration', (): void => {
    const links = workspaceNavigation(false);
    expect(links.map((link): string => link.id)).toEqual(['dashboard', 'connectors', 'files', 'insights', 'gettingStarted']);
    expect(links.map((link): string | undefined => link.icon)).toEqual(['dashboard', 'connectors', 'files', 'analytics', 'gettingStarted']);
    expect(links.map((link): string => link.href)).toEqual(['/dashboard', '/connectors', '/files', '/insights/agent-behaviour', '/getting-started']);
    expect(links.some((link): boolean => link.href.startsWith('/admin'))).toBe(false);
  });

  test('authorized workspace adds one divided Administration entry', (): void => {
    const links = workspaceNavigation(true);
    expect(links).toHaveLength(6);
    expect(links[5]).toEqual({
      id: 'administration', label: 'Administration', href: '/admin/connectors',
      icon: 'administration', startsSection: true
    });
  });

  test('account destinations are separate from both workspace and administration navigation', (): void => {
    expect(workspaceAccountLinks.map((link): readonly [string, string] => [link.label, link.href])).toEqual([
      ['Account settings', '/settings'],
      ['Access tokens', '/settings/tokens']
    ]);
  });

  test('administration sidebar shows only administration destinations', (): void => {
    expect(administrationNavigation.map((link): string => link.href)).toEqual([
      '/admin/connectors', '/admin/groups', '/admin/namespaces', '/admin/group-permissions/connectors',
      '/admin/insights/agent-behaviour', '/admin/agent-diagnostics'
    ]);
    expect(administrationNavigation.map((link): string | undefined => link.icon)).toEqual([
      'connectors', 'groups', 'files', 'permissions', 'analytics', 'administration'
    ]);
    expect(administrationNavigation.map((link): string => link.id)).toEqual([
      'connectors', 'groups', 'namespaces', 'groupPermissions', 'insights', 'agentDiagnostics'
    ]);
    expect(new Set(administrationNavigation.map((link): string => link.id)).size).toBe(6);
    expect(administrationNavigation.filter((link): boolean => link.startsSection === true).map((link): string => link.href)).toEqual([]);
  });
});
