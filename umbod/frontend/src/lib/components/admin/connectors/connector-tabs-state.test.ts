import { describe, expect, test } from 'vitest';
import { ConnectorTabsState, type ConnectorTab } from './connector-tabs-state.svelte';
import type { ConnectorCapability } from '$lib/admin/connector-capabilities';

describe('connector subpage navigation', (): void => {
  test('preserves current capability across every destination and follows input changes', (): void => {
    let capability: ConnectorCapability = 'prompts';
    let active: ConnectorTab = 'catalog';
    const state = new ConnectorTabsState(() => active, () => capability, () => ({ from: null, to: null }));
    expect(state.links.map((link): string => link.href)).toEqual([
      '/admin/connectors?capability=prompts', '/admin/openapi-connectors?capability=prompts', '/admin/downstream-mcp-connectors?capability=prompts'
    ]);
    capability = 'resources';
    active = 'openapi';
    expect(state.links.every((link): boolean => link.href.endsWith('?capability=resources'))).toBe(true);
    expect(state.activeId).toBe('openapi');
    expect(state.pending).toBe(false);
  });

  test('shows pending destinations only when navigating between connector subpages', (): void => {
    let target: { url: URL } | null = { url: new URL('https://umbod.test/admin/openapi-connectors') };
    const state = new ConnectorTabsState(() => 'catalog', () => 'tools', () => ({ from: { url: new URL('https://umbod.test/admin/connectors') }, to: target }));
    expect(state.activeId).toBe('openapi');
    expect(state.pending).toBe(true);
    target = { url: new URL('https://umbod.test/admin/connectors?connector=other') };
    expect(state.pending).toBe(false);
    target = { url: new URL('https://umbod.test/getting-started') };
    expect(state.activeId).toBe('catalog');
    expect(state.pending).toBe(false);
    target = null;
    expect(state.pending).toBe(false);
  });
});
