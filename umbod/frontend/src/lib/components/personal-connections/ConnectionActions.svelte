<script lang="ts">
  import { tick } from 'svelte';
  import type { ConnectionAction } from '$lib/personal-connections/presentation';
  import type { PersonalConnectionController } from '$lib/personal-connections/state/port';
  import { PersonalAccessViewState } from '$lib/personal-connections/state/access-view-state.svelte';
  import AdminSidebarActionMenu from '$lib/components/admin/shared/AdminSidebarActionMenu.svelte';

  let { state, onaction }: { state: PersonalConnectionController; onaction?: () => void } = $props();
  const view = new PersonalAccessViewState(() => state);
  const reasonId = $props.id();

  async function act(action: ConnectionAction): Promise<void> {
    onaction?.();
    const operation = view.perform(action);
    const transfersFocus = action === 'continue-sign-in' || action === 'sign-in';
    if (transfersFocus) await operation;
    await tick();
    if (!transfersFocus || !state.authorizationOpened) view.focusTrigger();
    await operation;
  }
</script>

<div class="connection-actions" bind:this={view.root}>
  <AdminSidebarActionMenu open={view.menuOpen} label={`Personal access actions for ${state.selection.display_name}`} onopenchange={view.setMenuOpen}>
    {#snippet menu()}
      {#each view.menuActions as action (action.id)}
        <button type="button" role="menuitem" disabled={action.disabled} aria-describedby={action.reason ? `${reasonId}-${action.id}` : undefined} title={action.reason || undefined} data-destructive={action.destructive ? 'true' : undefined} onclick={() => act(action.id)}>{action.label}</button>
        {#if action.reason}<span id={`${reasonId}-${action.id}`} class="sr-only">{action.reason}</span>{/if}
      {/each}
    {/snippet}
  </AdminSidebarActionMenu>
</div>

<style>
  .connection-actions { flex: 0 0 auto; padding-right: 0.5rem; }
  .connection-actions :global([role='menu']) { min-width: 14rem; }
  .connection-actions :global([data-destructive='true']) { color: var(--admin-danger); }
  .sr-only { clip-path: inset(50%); height: 1px; overflow: hidden; position: absolute; white-space: nowrap; width: 1px; }
</style>
