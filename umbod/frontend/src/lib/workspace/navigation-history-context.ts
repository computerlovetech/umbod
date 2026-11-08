import { getContext, setContext } from 'svelte';
import type { WorkspaceNavigationHistory } from './navigation-history.svelte';

export const workspaceNavigationHistoryKey = Symbol('workspace-navigation-history');

export function provideWorkspaceNavigationHistory(history: WorkspaceNavigationHistory): void {
  setContext(workspaceNavigationHistoryKey, history);
}

export function useWorkspaceNavigationHistory(): WorkspaceNavigationHistory | undefined {
  return getContext<WorkspaceNavigationHistory | undefined>(workspaceNavigationHistoryKey);
}
