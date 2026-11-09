import { describe, expect, test } from 'vitest';
import { filesystemFixture, filesystemNode, rootId } from '$lib/files/fixtures.test-support';
import { InMemoryFilesApi } from '$lib/files/infrastructure/in-memory-api.test-support';
import { NodeUpdateState } from '$lib/files/state/node-update-state.svelte';
import { DescriptionState } from '$lib/files/state/description-state.svelte';
import { NodeActionsState } from './node-actions-state.svelte';

describe('node details state', (): void => {
  test('details eligibility uses discover only and reads live authoritative data', (): void => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const update = new NodeUpdateState(api.filesystem, (): void => {}, async (): Promise<void> => {});
    const description = new DescriptionState(api.filesystem, (): void => {}, async (): Promise<void> => {});
    let node = filesystemNode({ permissions: { can_discover: true, can_read: false, can_write: false, can_delete: false, can_share: false } });
    const state = new NodeActionsState(() => ({ update, description, node, mutationsAllowed: false }));
    expect(state.available).toBe(true);
    state.setOpen(true);
    state.showDetails();
    expect(state.open).toBe(false);
    expect(state.detailsNode).toBe(node);
    node = filesystemNode({ ...node, name: 'Current name', revision: 2 });
    expect(state.detailsNode?.name).toBe('Current name');
    state.closeDetails();
    expect(state.detailsNode).toBeUndefined();
  });

  test('write or share permissions do not substitute for discover permission', (): void => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const update = new NodeUpdateState(api.filesystem, (): void => {}, async (): Promise<void> => {});
    const description = new DescriptionState(api.filesystem, (): void => {}, async (): Promise<void> => {});
    const node = filesystemNode({ permissions: { can_discover: false, can_read: true, can_write: true, can_delete: true, can_share: true } });
    const state = new NodeActionsState(() => ({ update, description, node }));
    expect(state.canViewDetails).toBe(false);
    state.showDetails();
    expect(state.detailsNode).toBeUndefined();
  });
});
