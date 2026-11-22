<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import InsightsFrame from '#lib/components/shared/workspace/InsightsFrame.svelte';
  import type { SubpageLink } from '#lib/components/shared/workspace/SubpageNavigation.svelte';
  import { personalInsightsHref, personalInsightsLogsHref } from '#lib/workspace/navigation.js';
  import { useWorkspace } from '#lib/workspace/workspace-context.js';
  import type { LayoutProps } from './$types';

  let { children }: LayoutProps = $props();
  const workspace = useWorkspace();
  const links: readonly SubpageLink[] = [
    { id: 'behaviour', label: 'Agent behaviour', href: personalInsightsHref },
    { id: 'logs', label: 'Log analytics', href: personalInsightsLogsHref }
  ];

  onMount((): void => {
    if (workspace.access.adminAccess !== 'checking') observeVisibility();
  });

  function observeVisibility(): void {
    if (document.visibilityState === 'visible') void workspace.refreshPersonal();
    else workspace.suspendPersonal();
  }
</script>

<svelte:document onvisibilitychange={observeVisibility} />

<InsightsFrame {links} activeId={page.url.pathname === personalInsightsLogsHref ? 'logs' : 'behaviour'}>
  {#if workspace.personalChecking}
    <p class="admin-message" role="status">Loading insights…</p>
  {:else if workspace.personalUnavailable}
    <p class="admin-message" role="alert">Could not load your account.</p>
    <Button onclick={() => workspace.refreshPersonal()}>Try again</Button>
  {:else if workspace.personalIdentity.kind === 'visible'}
    {#key workspace.personalIdentity.hiddenValues.id}
      {@render children()}
    {/key}
  {:else}
    <p class="admin-message" role="status">Sign in to view your insights.</p>
  {/if}
</InsightsFrame>
