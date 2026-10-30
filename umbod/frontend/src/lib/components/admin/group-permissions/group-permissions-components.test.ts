import { render } from 'svelte/server';
import { describe, expect, test } from 'vitest';
import GroupPermissionsManager from './GroupPermissionsManager.svelte';
import { GroupPermissionsState, type GroupPermissionsInitialData } from './group-permissions-state.svelte';


const initialData = (): GroupPermissionsInitialData => ({
  groups: [{ groupId: 'team', label: 'Team label', description: 'Shared team description', revision: 2 }],
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
  test('keeps catalogue guidance out of the permission editor', (): void => {
    const data = initialData();
    data.preloadedGroup = { groupId: 'team', connectorIds: [], capabilities: [] };
    const body = render(GroupPermissionsManager, { props: { state: new GroupPermissionsState(data, null, null) } }).body;
    expect(body).not.toContain('Groups are shared with filesystem access');
    expect(body).not.toContain('Registration alone grants no access');
    expect(body).not.toContain('Delete group');
    expect(body).toContain('Available server access');
    expect(body).not.toContain('Saved grants for unavailable connectors');
  });

  test('labels unavailable connector and capability-only grants with explicit staging buttons and native save form', (): void => {
    const state = new GroupPermissionsState(initialData(), null, null);
    const body = render(GroupPermissionsManager, { props: { state } }).body.replace(/<!--.*?-->/g, '');
    expect(body).toContain('aria-labelledby="unavailable-connector-grants-heading"');
    expect(body).toContain('Saved grants for unavailable connectors');
    expect(body).toContain('may be unpublished');
    expect(body).toContain('Changes apply only after Save permissions');
    expect(body).toMatch(/<button[^>]*type="button"[^>]*aria-label="Remove saved grants for unpublished"[^>]*>Remove saved grants<\/button>/);
    expect(body).toMatch(/<button[^>]*type="button"[^>]*aria-label="Remove saved grants for capability-only"[^>]*>Remove saved grants<\/button>/);
    expect(body).not.toContain('Remove saved grants for available');
    expect(body).not.toContain('Remove saved grants for unknown');
    expect(body).toContain('Available server access');
    expect(body).toContain('<form');
    expect(body).toMatch(/<button[^>]*type="submit"/);
    expect(body).not.toContain('data-operation=');
    expect(body).not.toContain('name="permissionSet"');
    expect(body).toContain('Save permissions');
    expect(body).not.toContain('Republish');
  });

  test('does not invent saved grants when all selected targets are assignable', (): void => {
    const data = initialData();
    data.preloadedGroup = { groupId: 'team', connectorIds: ['available'], capabilities: [] };
    const body = render(GroupPermissionsManager, { props: { state: new GroupPermissionsState(data, null, null) } }).body;
    expect(body).not.toContain('Saved grants for unavailable connectors');
    expect(body).toContain('Available server access');
  });

  test('keeps long identifiers in the accessible name rather than the nonwrapping button text', (): void => {
    const data = initialData();
    const connectorId = 'unavailable-'.repeat(50);
    data.preloadedGroup = { groupId: 'team', connectorIds: [connectorId], capabilities: [] };
    const body = render(GroupPermissionsManager, { props: { state: new GroupPermissionsState(data, null, null) } }).body.replace(/<!--.*?-->/g, '');
    expect(body).toContain(`aria-label="Remove saved grants for ${connectorId}"`);
    expect(body).toContain('>Remove saved grants</button>');
    expect(body).not.toContain('>Remove saved grants for ');
  });

  test('does not offer cleanup without ready selected detail', (): void => {
    const data = initialData();
    data.preloadedGroup = null;
    const body = render(GroupPermissionsManager, { props: { state: new GroupPermissionsState(data, null, null) } }).body;
    expect(body).not.toContain('Saved grants for unavailable connectors');
    expect(body).not.toContain('Remove saved grants');
  });
});
