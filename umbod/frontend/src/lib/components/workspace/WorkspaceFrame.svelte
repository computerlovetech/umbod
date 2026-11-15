<script lang="ts">
  import { onMount, untrack, type Snippet } from 'svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import type { WorkspaceApi } from '$lib/workspace/api';
  import { workspaceApi } from '$lib/workspace/infrastructure/workspace-api';
  import { WorkspaceAccessState } from '$lib/workspace/workspace-access-state.svelte';
  import { WorkspaceScope } from '$lib/workspace/workspace-scope.svelte';
  import { provideWorkspace } from '$lib/workspace/workspace-context';
  import { WorkspaceNavigationState } from '$lib/workspace/workspace-navigation-state.svelte';
  import { workspaceNavigation, workspacePresentation } from '$lib/workspace/navigation';
  import { logoutNavigation } from '$lib/admin/infrastructure/logout';
  import WorkspaceShell from '$lib/components/shared/workspace/WorkspaceShell.svelte';

  let { children, pathname, accountIdentity, createWorkspaceApi = workspaceApi }: {
    children: Snippet;
    pathname: string;
    accountIdentity: HeaderAccountIdentityState;
    createWorkspaceApi?: () => WorkspaceApi;
  } = $props();

  function createAccess(): WorkspaceAccessState {
    return new WorkspaceAccessState(createWorkspaceApi(), () => accountIdentity);
  }

  const access = createAccess();
  const scope = new WorkspaceScope(access);
  const navigation = new WorkspaceNavigationState(() => pathname);
  provideWorkspace(scope);

  $effect.pre(() => {
    const identity = accountIdentity;
    untrack(() => access.observeIdentitySource(identity));
  });

  onMount(() => {
    void access.load();
    return scope.dispose;
  });

  async function logout(): Promise<void> {
    scope.dispose();
    await logoutNavigation.logout();
  }
</script>

<WorkspaceShell {...workspacePresentation} navigationItems={workspaceNavigation(access.adminAccess === 'allowed')} activeItem={navigation.activeItem} accountIdentity={access.effectiveAccountIdentity} logout={{ logout }} contentWidth="wide">
  {@render children()}
</WorkspaceShell>
