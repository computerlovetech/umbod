import { afterEach, describe, expect, it } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import GroupPermissionsManager from './GroupPermissionsManager.svelte';
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
