import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import GroupPermissionsManager from './GroupPermissionsManager.svelte';
import { InMemoryGroupPermissionsLoader } from './group-permissions-loader';
import type { GroupPermissionSet, UpdateGroupPermissionsRequest } from '$lib/admin/group-permissions';
import { GroupPermissionsState, type GroupPermissionsInitialData } from './group-permissions-state.svelte';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

function initialData(): GroupPermissionsInitialData {
  return {
    groups: [
      { groupId: 'a', label: 'Operators', description: 'Original description', revision: 1 },
      { groupId: 'b', label: 'Readers', description: 'Reader description', revision: 1 }
    ],
    preloadedGroup: { groupId: 'a', connectorIds: [], capabilities: [] },
    assignableTargets: [{ id: 'reports', displayName: 'Reports', description: '', capabilities: [] }],
    exactMatchGuidance: '', initialTarget: null, originHref: null
  };
}

describe('unavailable connector removal interactions', () => {
  it.each(['success', 'failure'] as const)('shows named removal-only entries and preserves unrelated grants on save %s', async (outcome): Promise<void> => {
    const initial = initialData();
    const saved: GroupPermissionSet = {
      groupId: 'a',
      connectorIds: ['retired', 'reports', 'other'],
      capabilities: [
        { connectorId: 'retired', kind: 'tool', key: 'search' },
        { connectorId: 'retired', kind: 'prompt', key: 'summarize' },
        { connectorId: 'reports', kind: 'tool', key: 'read' },
        { connectorId: 'other', kind: 'resource', key: 'file' }
      ]
    };
    initial.preloadedGroup = saved;
    const canonical: GroupPermissionSet = {
      ...saved,
      connectorIds: ['reports', 'other'],
      capabilities: saved.capabilities.filter((capability) => capability.connectorId !== 'retired')
    };
    const loader = new InMemoryGroupPermissionsLoader(new Map([['a', saved]]), initial.assignableTargets, [
      { id: 'retired', displayName: 'Retired search', publicationStatus: 'unpublished' }
    ]);
    const save = vi.fn(async (_groupId: string, _changes: UpdateGroupPermissionsRequest): Promise<GroupPermissionSet> => {
      if (outcome === 'failure') throw new Error('Unavailable');
      return canonical;
    });
    const state = new GroupPermissionsState(initial, null, null, loader, { save });
    const target = document.createElement('div');
    document.body.append(target);
    component = mount(GroupPermissionsManager, { target, props: { state } });
    await tick();
    const section = target.querySelector<HTMLElement>('section[aria-labelledby="unavailable-connector-grants-heading"]')!;
    expect(section).not.toBeNull();
    expect(section.textContent).toContain('Unavailable connectors');
    await vi.waitFor(() => expect(section.textContent).toContain('Unpublished'));
    expect(section.querySelector('input')).toBeNull();
    expect([...target.querySelectorAll('h3')].map((heading) => heading.textContent)).toEqual(['Unavailable connectors', 'Connectors & permissions']);
    const remove = section.querySelector<HTMLButtonElement>('button[aria-label="Remove saved grants for Retired search"]')!;
    expect(remove).not.toBeNull();
    const row = remove.closest('li')!;
    expect(row.textContent).toContain('retired');
    const submit = target.querySelector<HTMLButtonElement>('button[type="submit"]')!;
    expect(submit.disabled).toBe(true);
    remove.click();
    await tick();
    expect(section.querySelector('button[aria-label="Remove saved grants for Retired search"]')).toBeNull();
    expect(submit.disabled).toBe(false);
    submit.click();
    await vi.waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    await tick();
    expect(save).toHaveBeenCalledWith('a', {
      connectors: [{ connector_id: 'retired', permission_status: 'disabled' }],
      capabilities: [
        { connector_id: 'retired', capability_kind: 'prompt', capability_key: 'summarize', permission_status: 'disabled' },
        { connector_id: 'retired', capability_kind: 'tool', capability_key: 'search', permission_status: 'disabled' }
      ]
    });
    expect(state.selectedPermissionSet).toEqual(canonical);
    expect(target.querySelector('button[aria-label="Remove saved grants for Retired search"]')).toBeNull();
    if (outcome === 'success') {
      expect(submit.disabled).toBe(true);
      expect(state.hasUnsavedChanges).toBe(false);
      expect(state.groups.find((group) => group.groupId === 'a')).toEqual(canonical);
    } else {
      expect(target.querySelector('[role="status"]')?.getAttribute('aria-label')).toContain('Permissions could not be saved');
      expect(submit.disabled).toBe(false);
      expect(state.hasUnsavedChanges).toBe(true);
      expect(state.groups.find((group) => group.groupId === 'a')).toEqual(saved);
    }
    state.dispose();
  });
});

describe('reactive permission catalogue integration', () => {
  it('retains staged detail through catalogue changes and clears controls when the selected group is removed', async (): Promise<void> => {
    const initial = initialData();
    const state = new GroupPermissionsState(initial, null, null);
    const target = document.createElement('div');
    document.body.append(target);
    component = mount(GroupPermissionsManager, { target, props: { state } });
    flushSync();
    const toggle = target.querySelector<HTMLInputElement>('label[aria-label="Reports access"] input[type="checkbox"]')!;
    const save = target.querySelector<HTMLButtonElement>('button[type="submit"]')!;
    const form = target.querySelector('form');
    expect(toggle.checked).toBe(false);
    expect(save.disabled).toBe(true);
    toggle.click();
    await tick();
    const draft = state.selectedPermissionChangesJson;
    expect(draft).toContain('enabled');
    expect(draft).toContain('reports');
    expect(toggle.checked).toBe(true);
    expect(save.disabled).toBe(false);
    const renamed = { ...initial.groups[0], label: 'Renamed operators', description: 'New description', revision: 2 };
    const added = { groupId: 'c', label: 'Auditors', description: 'Audit description', revision: 1 };
    state.synchronizeCatalogue([renamed, added]);
    await tick();
    expect(state.selectedPermissionChangesJson).toBe(draft);
    expect(target.querySelector('label[aria-label="Reports access"] input[type="checkbox"]')).toBe(toggle);
    expect(toggle.checked).toBe(true);
    expect(target.querySelector('button[type="submit"]')).toBe(save);
    expect(save.disabled).toBe(false);
    expect(target.querySelector('form')).toBe(form);
    state.synchronizeCatalogue([added]);
    await tick();
    expect(state.selectedGroupId).toBeNull();
    expect(state.selectedPermissionChangesJson).toBe(JSON.stringify({ connectors: [], capabilities: [] }));
    expect(target.querySelector('input[type="checkbox"]')).toBeNull();
    expect(target.querySelector('button[type="submit"]')).toBeNull();
    expect(target.querySelector('form')).toBeNull();
    expect(target.textContent).toContain('Select a group to edit permissions');
  });
});
