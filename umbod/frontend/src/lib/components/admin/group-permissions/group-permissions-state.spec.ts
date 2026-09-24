import { describe, expect, test } from 'vitest';
import {
  addGroupToState,
  hasUnsavedChangesInState,
  persistedPermissionSetFromState,
  stagedPermissionSetFromState
} from './group-permissions-state.svelte';

describe('staged permission group baseline', () => {
  test('new group stages against an empty non-persisted baseline', () => {
    const state = addGroupToState({ groups: [] }, 'future-team');

    expect(stagedPermissionSetFromState(state, 'future-team')).toEqual({
      groupId: 'future-team',
      connectorIds: [],
      capabilities: []
    });
    expect(persistedPermissionSetFromState(state, 'future-team')).toBeNull();
    expect(hasUnsavedChangesInState(state, 'future-team')).toBe(true);
  });
});
