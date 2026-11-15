import { createContext } from 'svelte';
import type { WorkspaceScope } from './workspace-scope.svelte';

export const [useWorkspace, provideWorkspace] = createContext<WorkspaceScope>();
