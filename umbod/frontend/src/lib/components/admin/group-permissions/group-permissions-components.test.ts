import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import GroupPermissionsManager from './GroupPermissionsManager.svelte';
import type { GroupPermissionsInitialData } from './group-permissions-state.svelte';

vi.mock('$lib/components/feedback', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }));

const initialData = (): GroupPermissionsInitialData => ({
  groups: [{ groupId: 'team' }],
  preloadedGroup: {
    groupId: 'team',
    connectorIds: ['unpublished', 'available'],
    capabilities: [{ connectorId: 'capability-only', kind: 'tool', key: 'saved-tool' }]
  },
  assignableTargets: [{ id: 'available', displayName: 'Available server', description: '', capabilities: [] }],
  exactMatchGuidance: '',
  initialTarget: null,
  originHref: null
});

describe('unavailable saved grant presentation', () => {
  test('labels unavailable connector and capability-only grants with explicit staging buttons and existing save form', () => {
    const body = render(GroupPermissionsManager, { props: { data: initialData() } }).body.replace(/<!--.*?-->/g, '');
    expect(body).toContain('aria-labelledby="unavailable-connector-grants-heading"');
    expect(body).toContain('Saved grants for unavailable connectors');
    expect(body).toContain('may be unpublished');
    expect(body).toContain('Changes apply only after Save permissions');
    expect(body).toMatch(/<button[^>]*type="button"[^>]*aria-label="Remove saved grants for unpublished"[^>]*>Remove saved grants<\/button>/);
    expect(body).toMatch(/<button[^>]*type="button"[^>]*aria-label="Remove saved grants for capability-only"[^>]*>Remove saved grants<\/button>/);
    expect(body).not.toContain('Remove saved grants for available');
    expect(body).not.toContain('Remove saved grants for unknown');
    expect(body).toContain('Available server access');
    expect(body).toContain('data-operation="saveGroupPermissions"');
    expect(body).toContain('Save permissions');
    expect(body).not.toContain('Republish');
  });

  test('does not invent saved grants when all selected targets are assignable', () => {
    const data = initialData();
    data.preloadedGroup = { groupId: 'team', connectorIds: ['available'], capabilities: [] };
    const body = render(GroupPermissionsManager, { props: { data } }).body;
    expect(body).not.toContain('Saved grants for unavailable connectors');
    expect(body).toContain('Available server access');
  });

  test('keeps long identifiers in the accessible name rather than the nonwrapping button text', () => {
    const data = initialData();
    const connectorId = 'unavailable-'.repeat(50);
    data.preloadedGroup = { groupId: 'team', connectorIds: [connectorId], capabilities: [] };
    const body = render(GroupPermissionsManager, { props: { data } }).body.replace(/<!--.*?-->/g, '');
    expect(body).toContain(`aria-label="Remove saved grants for ${connectorId}"`);
    expect(body).toContain('>Remove saved grants</button>');
    expect(body).not.toContain('>Remove saved grants for ');
  });

  test('does not offer cleanup without ready selected detail', () => {
    const data = initialData();
    data.preloadedGroup = null;
    const body = render(GroupPermissionsManager, { props: { data } }).body;
    expect(body).not.toContain('Saved grants for unavailable connectors');
    expect(body).not.toContain('Remove saved grants');
  });
});
