import { afterEach, describe, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { fileId, filesystemFixture, filesystemNode, folderId, rootId } from '$lib/files/fixtures.test-support';
import type { NodeSummary } from '$lib/files/domain/schemas';
import { InMemoryFilesApi } from '$lib/files/infrastructure/in-memory-api.test-support';
import { FilesState } from '$lib/files/state/files-state.svelte';
import { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
import { UploadState } from '$lib/files/state/upload-state.svelte';
import FilesContent from './FilesContent.svelte';
import NodeActions from './NodeActions.svelte';
import { NodeDetailsInputs } from './node-details-inputs.svelte.test-support';
import { NodeUpdateState } from '$lib/files/state/node-update-state.svelte';
import { DescriptionState } from '$lib/files/state/description-state.svelte';

let component: ReturnType<typeof mount> | undefined;
let files: FilesState | undefined;

afterEach(async (): Promise<void> => {
  files?.dispose();
  if (component) await unmount(component);
  files = undefined;
  component = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function button(label: string, scope: ParentNode = document): HTMLButtonElement {
  const result = Array.from(scope.querySelectorAll<HTMLButtonElement>('button')).find((entry) => entry.textContent?.trim() === label || entry.getAttribute('aria-label') === label);
  expect(result, label).toBeDefined();
  return result!;
}

function value(label: string, list = 'Item details'): string | null {
  const term = Array.from(document.querySelectorAll(`dialog dl[aria-label="${list}"] dt`)).find((entry) => entry.textContent === label);
  expect(term, label).toBeDefined();
  return term!.nextElementSibling!.textContent;
}

async function setup(permissions?: NodeSummary['permissions']): Promise<{ state: FilesState; api: InMemoryFilesApi }> {
  const fixture = permissions ? filesystemFixture.map((node) => filesystemNode({ ...node, permissions })) : filesystemFixture;
  const api = new InMemoryFilesApi(rootId, fixture);
  if (permissions) {
    const browse = api.filesystem.browse;
    vi.spyOn(api.filesystem, 'browse').mockImplementation(async (target, signal) => {
      const result = await browse(target, signal);
      return { ...result, node: { ...result.node, permissions }, entries: result.entries.map((entry) => ({ ...entry, permissions })), capabilities: result.capabilities.map((entry) => ({ ...entry, rename: false, move: false, edit_description: false, delete: false, share: false })) };
    });
  }
  const state = new FilesState(api);
  files = state;
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(FilesContent, { target, props: { state, folder: new NewFolderState(api, state), upload: new UploadState(api, state), signIn: vi.fn() } });
  await state.load(folderId);
  await tick();
  return { state, api };
}

async function setupActions(): Promise<NodeDetailsInputs> {
  const node = filesystemNode({ id: folderId, parent_id: rootId, name: 'Projects' });
  const inputs = new NodeDetailsInputs(node);
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(NodeActions, { target, props: {
    get node(): NodeSummary | undefined { return inputs.node; },
    name: node.name,
    update: new NodeUpdateState(api.filesystem, (): void => {}, async (): Promise<void> => {}),
    description: new DescriptionState(api.filesystem, (): void => {}, async (): Promise<void> => {}),
    signIn: (): void => {}
  } });
  await tick();
  return inputs;
}

async function details(scope: ParentNode = document): Promise<HTMLButtonElement> {
  const trigger = scope.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]');
  expect(trigger).not.toBeNull();
  trigger!.click();
  await tick();
  button('View details').click();
  await tick();
  expect(document.querySelector('dialog')).not.toBeNull();
  return trigger!;
}

describe('node details', (): void => {
  test.each([true, false])('read=%s exposes details without mutation or sharing controls or extra requests', async (can_read): Promise<void> => {
    const { api } = await setup({ can_discover: true, can_read, can_write: false, can_delete: false, can_share: false });
    const browse = vi.spyOn(api.filesystem, 'browse').mockClear();
    const probe = vi.spyOn(api.filesystem, 'checkUpdateEligibility');
    const remove = vi.spyOn(api.filesystem, 'deleteFile');
    const row = document.querySelector('tbody')!;
    expect(row.textContent).toContain(can_read ? 'Read only' : 'Details only');
    button('Actions for “Notes.txt”', row).click();
    await tick();
    expect(Array.from(document.querySelectorAll('[role="menuitem"]')).map((entry) => entry.textContent?.trim())).toEqual(['View details']);
    button('View details').click();
    await tick();
    expect(value('Name')).toBe('Notes.txt');
    expect(value('Type')).toBe('File');
    expect(value('Content type')).toBe('text/plain');
    expect(value('Description')).toBe('Not specified');
    expect(value('Created')).toContain('2026');
    expect(value('Updated')).toContain('2026');
    expect(value('Revision')).toBe('1');
    for (const [label, allowed] of [['Discover', true], ['Read', can_read], ['Write', false], ['Delete', false], ['Share', false]] as const) {
      expect(value(label, 'Your permissions')).toBe(allowed ? 'Allowed' : 'Not allowed');
    }
    expect(browse).not.toHaveBeenCalled();
    expect(probe).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
  });

  test.each(['Close', 'Escape'])('%s restores focus to the same row menu trigger', async (method): Promise<void> => {
    await setup();
    const trigger = await details(document.querySelector('tbody')!);
    if (method === 'Escape') document.querySelector('dialog')!.dispatchEvent(new Event('cancel', { cancelable: true }));
    else button('Close', document.querySelector('dialog')!).click();
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
    await vi.waitFor((): void => expect(document.activeElement).toBe(trigger));
  });

  test('current folders omit missing content type and show authoritative live updates', async (): Promise<void> => {
    const inputs = await setupActions();
    await details();
    expect(value('Type')).toBe('Folder');
    expect(document.querySelector('dialog')!.textContent).not.toContain('Content type');
    inputs.select(filesystemNode({ ...inputs.node!, name: 'Renamed', revision: 2, metadata: { content_type: {}, attributes: { description: 'Current description' } } }));
    await tick();
    expect(value('Name')).toBe('Renamed');
    expect(value('Description')).toBe('Current description');
    expect(value('Revision')).toBe('2');
  });

  test('access loss closes details and restored access does not reopen them', async (): Promise<void> => {
    const inputs = await setupActions();
    await details();
    const node = inputs.node!;
    inputs.select(filesystemNode({ ...node, revision: 2, permissions: { ...node.permissions, can_discover: false } }));
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
    inputs.select(filesystemNode({ ...node, revision: 3 }));
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
  });

  test('navigation closes details without reopening the previous selection', async (): Promise<void> => {
    const { state } = await setup();
    await details();
    await state.load(fileId);
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
    await state.load(folderId);
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
  });

  test('changing live selection closes details without reopening when returning', async (): Promise<void> => {
    const inputs = await setupActions();
    const previous = inputs.node!;
    await details();
    inputs.select(filesystemNode({ id: fileId, parent_id: folderId, name: 'Other.txt', kind: 'file' }));
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
    inputs.select(previous);
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
  });

  test('personal root retains only details in its current-node menu', async (): Promise<void> => {
    const { state } = await setup();
    await state.load(rootId);
    await tick();
    const trigger = document.querySelector<HTMLButtonElement>('.node-identity')!.parentElement!.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]');
    expect(trigger).not.toBeNull();
    trigger!.click();
    await tick();
    expect(Array.from(document.querySelectorAll('[role="menuitem"]')).map((entry) => entry.textContent?.trim())).toEqual(['View details']);
    button('View details').click();
    await tick();
    expect(value('Type')).toBe('Folder');
    expect(value('Name')).toBe('Files');
    expect(document.querySelector('.node-identity')!.textContent).toContain('Can edit');
  });
});
