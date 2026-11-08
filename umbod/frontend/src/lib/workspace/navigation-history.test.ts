import { describe, expect, test } from 'vitest';
import { WorkspaceNavigationHistory } from './navigation-history.svelte';

function location(path: string): URL {
  return new URL(path, 'https://umbod.test');
}

describe('workspace navigation history', (): void => {
  test('direct administration entry returns to Dashboard without an entrance animation', (): void => {
    const history = new WorkspaceNavigationHistory(location('/admin/groups'), true);
    expect(history.returnHref).toBe('/dashboard');
    expect(history.transition).toBeNull();
  });

  test('remembers successful personal locations including query and fragment', (): void => {
    const history = new WorkspaceNavigationHistory(location('/dashboard'), true);
    history.completeNavigation(location('/files?sort=name#selected'), true);
    history.startNavigation(location('/files?sort=name#selected'), location('/admin/connectors'), true);
    history.completeNavigation(location('/admin/connectors'), true);
    history.completeNavigation(location('/admin/groups'), true);
    expect(history.returnHref).toBe('/files?sort=name#selected');
  });

  test.each(['/login', '/admin', '/admin/groups', '/administrator', '/files-other', 'https://other.test/files'])('ignores non-workspace or administrative return destination %s', (path: string): void => {
    const history = new WorkspaceNavigationHistory(location('/getting-started/telemetry'), true);
    history.completeNavigation(location(path), true);
    expect(history.returnHref).toBe('/getting-started/telemetry');
  });

  test.each([
    ['/dashboard', '/admin/connectors', 'forward'],
    ['/admin/groups', '/getting-started/telemetry', 'backward'],
    ['/admin/connectors', '/admin/groups', null],
    ['/dashboard', '/files', null],
    ['/login', '/admin/groups', null],
    ['/files-other', '/admin/groups', null],
    ['/dashboard', 'https://other.test/admin/groups', null]
  ] as const)('navigation from %s to %s selects %s sidebar motion', (from: string, to: string, transition): void => {
    const history = new WorkspaceNavigationHistory(location(from), true);
    history.startNavigation(location(from), location(to), true);
    expect(history.transition).toBe(transition);
  });

  test('same-context and external navigation clear previous transition without changing the remembered page', (): void => {
    const history = new WorkspaceNavigationHistory(location('/files'), true);
    history.startNavigation(location('/files'), location('/admin/connectors'), true);
    expect(history.transition).toBe('forward');
    history.startNavigation(location('/admin/connectors'), location('/admin/groups'), true);
    expect(history.transition).toBeNull();
    history.startNavigation(location('/admin/groups'), null, true);
    expect(history.transition).toBeNull();
    expect(history.returnHref).toBe('/files');
  });

  test('navigation attempts do not replace the last successfully visited workspace page', (): void => {
    const history = new WorkspaceNavigationHistory(location('/files'), true);
    history.startNavigation(location('/files'), location('/getting-started'), true);
    expect(history.returnHref).toBe('/files');
    history.completeNavigation(location('/getting-started'), true);
    expect(history.returnHref).toBe('/getting-started');
  });

  test('captures fragment and shallow-history changes from the current successful source', (): void => {
    const history = new WorkspaceNavigationHistory(location('/files?sort=name'), true);
    history.startNavigation(location('/files?sort=date#document'), location('/admin/groups'), true);
    expect(history.returnHref).toBe('/files?sort=date#document');
    history.startNavigation(location('/admin/groups'), location('/files?sort=name#earlier'), true);
    history.completeNavigation(location('/files?sort=name#earlier'), true);
    history.startNavigation(location('/files?sort=name#back'), location('/admin/groups'), true);
    expect(history.returnHref).toBe('/files?sort=name#back');
  });

  test('error locations never replace a successful return destination and clear pending entrance motion', (): void => {
    const history = new WorkspaceNavigationHistory(location('/files'), true);
    history.completeNavigation(location('/files/missing'), false);
    history.startNavigation(location('/files/missing'), location('/admin/groups'), false);
    history.completeNavigation(location('/admin/groups'), false);
    expect(history.returnHref).toBe('/files');
    expect(history.transition).toBeNull();
  });

  test('an unsuccessful initial workspace URL retains the Dashboard fallback', (): void => {
    const history = new WorkspaceNavigationHistory(location('/files/missing'), false);
    expect(history.returnHref).toBe('/dashboard');
  });

  test('histories remain isolated between application instances', (): void => {
    const first = new WorkspaceNavigationHistory(location('/files'), true);
    const second = new WorkspaceNavigationHistory(location('/admin/connectors'), true);
    first.completeNavigation(location('/getting-started/telemetry'), true);
    expect(first.returnHref).toBe('/getting-started/telemetry');
    expect(second.returnHref).toBe('/dashboard');
  });
});
