import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import { InMemoryFilesystemAdministration } from '$lib/admin/filesystem/in-memory';
import { InMemoryGroupCatalogue } from '$lib/admin/groups/in-memory';
import { rootPolicy } from '$lib/admin/filesystem/fixtures.test-support';
import { FilesystemAccessState } from './filesystem-access-state.svelte';
import FilesystemAccessEditor from './FilesystemAccessEditor.svelte';
import { FilesystemGroupEditorState } from './filesystem-group-editor-state.svelte';

const renderEditor = (state: FilesystemAccessState, editor = new FilesystemGroupEditorState(() => state)): string => render(FilesystemAccessEditor, { props: { state, editor } }).body;

describe('filesystem accessible presentation', () => {
  it('shows five controls and one save without owning the shared page or sidebar', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups: [{ group_id: 'operators', permissions: ['read', 'share'] }] })), new InMemoryGroupCatalogue([{ group_id: 'operators', label: 'operators', description: '', revision: 1 }]));
    await state.load();
    const body = renderEditor(state);
    for (const label of ['Browse root', 'Read', 'Create items', 'Delete', 'Share', 'Save permissions']) expect(body).toContain(label);
    expect(body.match(/type="checkbox"/g)).toHaveLength(5);
    expect(body.match(/ checked/g)).toHaveLength(2);
    expect(body.match(/<button[^>]*aria-label="Save permissions"/g)).toHaveLength(1);
    expect(body).not.toMatch(/<input(?![^>]*type="checkbox")/);
    for (const text of ['Manage groups', 'Root permissions apply here only', 'Reload', 'Discard changes', '<footer', '<h1', '<aside', '<dialog']) expect(body).not.toContain(text);
  });

  it('shows blocked groups without unusable permission actions', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', blocked_group_ids: ['blocked-group'] })), new InMemoryGroupCatalogue());
    await state.load();
    const body = renderEditor(state);
    expect(body).toContain('managed outside this editor');
    expect(body).not.toContain('type="checkbox"');
    expect(body).not.toContain('Save permissions');
  });

  it('keeps saving editable drafts reachable while a blocked group is selected', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', blocked_group_ids: ['blocked-group'] })), new InMemoryGroupCatalogue([{ group_id: 'blocked-group', label: 'blocked-group', description: '', revision: 1 }]));
    await state.load();
    state.setGroupPermissions('editable', ['read']);
    const body = renderEditor(state);
    expect(body).toContain('managed outside this editor');
    expect(body).not.toContain('type="checkbox"');
    expect(body).toContain('Save permissions');
    await state.save();
    expect(state.saved?.groups).toEqual([{ group_id: 'editable', permissions: ['read'] }]);
  });

  it('confirms clearing configurable permissions during empty setup', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy()), new InMemoryGroupCatalogue());
    await state.load();
    expect(renderEditor(state)).toContain('Save to finish setup.');
    await state.save();
    const body = renderEditor(state);
    expect(body).toContain('Clear configurable group permissions?');
    expect(body).toContain('Clear group permissions');
    expect(body).toContain('Configurable group permissions will be cleared. Other access rules remain unchanged.');
  });

  it('shows creation guidance only when Browse root is unchecked', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy()), new InMemoryGroupCatalogue([{ group_id: 'creators', label: 'creators', description: '', revision: 1 }]));
    await state.load();
    const editor = new FilesystemGroupEditorState(() => state);
    const guidance = 'Also select Browse root to allow creation.';
    expect(renderEditor(state, editor)).not.toContain(guidance);
    editor.toggle('write', true);
    expect(renderEditor(state, editor)).toContain(guidance);
    editor.toggle('discover', true);
    expect(renderEditor(state, editor)).not.toContain(guidance);
  });
});
