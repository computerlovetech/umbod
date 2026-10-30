import { createContext } from 'svelte';
import type { GroupPermissionsWorkspaceState } from './group-permissions-workspace-state.svelte';

export const [getGroupPermissionsWorkspace, setGroupPermissionsWorkspace] = createContext<GroupPermissionsWorkspaceState>();
