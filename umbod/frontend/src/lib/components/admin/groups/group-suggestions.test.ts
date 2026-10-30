import { describe, expect, it, vi } from 'vitest';
import { InMemoryGroupCatalogue } from '$lib/admin/groups/in-memory';
import { InMemoryIdentityDirectory } from '$lib/identity-directory/in-memory.test-support';
import type { DirectoryGroups } from '$lib/identity-directory/domain/schemas';
import { GroupsState } from './groups-state.svelte';

const result: DirectoryGroups = { issuer: 'issuer', claim: 'groups', groups: [{ value: ' Exact / Team ', first_seen_at: '2026-01-01T00:00:00Z', last_seen_at: '2026-01-01T00:00:00Z' }], has_more: false };

describe('optional provider group suggestions', () => {
  it('loads only on create, searches exact input without changing drafts and fences obsolete results', async (): Promise<void> => {
    const directory = new InMemoryIdentityDirectory(result);
    const pending: Array<(groups: DirectoryGroups) => void> = [];
    const list = vi.spyOn(directory, 'list').mockImplementation(() => new Promise((resolve) => { pending.push(resolve); }));
    const state = new GroupsState(new InMemoryGroupCatalogue(), [], directory);
    expect(list).not.toHaveBeenCalled();
    state.create();
    state.setLabel('Draft');
    state.setDescription('Keep');
    state.setGroupId('Exact');
    expect(list).toHaveBeenLastCalledWith({ query: 'Exact', limit: 50 });
    pending[1](result);
    await Promise.resolve();
    expect(state.suggestions.options).toEqual([' Exact / Team ']);
    pending[0]({ ...result, groups: [] });
    await Promise.resolve();
    expect(state.suggestions.options).toEqual([' Exact / Team ']);
    expect([state.groupId, state.label, state.description]).toEqual(['Exact', 'Draft', 'Keep']);
    state.setGroupId('manual');
    state.cancel();
    pending[2](result);
    await Promise.resolve();
    expect(state.suggestions.options).toEqual([]);
    state.edit({ group_id: 'fixed', label: 'Fixed', description: '', revision: 1 });
    state.setGroupId('changed');
    expect(state.groupId).toBe('fixed');
    expect(list).toHaveBeenCalledTimes(3);
    state.dispose();
  });
  it('silently falls back to exact manual creation when directory lookup fails', async (): Promise<void> => {
    const directory = new InMemoryIdentityDirectory();
    vi.spyOn(directory, 'list').mockRejectedValue(new Error('unavailable'));
    const catalogue = new InMemoryGroupCatalogue();
    const state = new GroupsState(catalogue, [], directory);
    state.create();
    state.setGroupId(' Manual / ');
    state.setLabel('Manual');
    await Promise.resolve();
    expect(state.error).toBe('');
    expect(state.suggestions.options).toEqual([]);
    await state.save();
    expect((await catalogue.list())[0].group_id).toBe(' Manual / ');
  });
});
