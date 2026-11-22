<script lang="ts">
  import type { Snippet } from 'svelte';
  import GroupPermissionsTabs from './GroupPermissionsTabs.svelte';

  let { activeTab, description, backHref = null, actions, children }: {
    activeTab: 'connectors' | 'filesystem';
    description: string;
    backHref?: string | null;
    actions?: Snippet;
    children: Snippet;
  } = $props();
</script>

<section class="permission-page" aria-labelledby="group-permissions-title">
  <header class="page-header">
    <div>
    {#if backHref !== null}
      <a class="back-link" href={backHref}>← Back to OpenAPI connector</a>
    {/if}
    <h1 id="group-permissions-title" class="admin-title">Permissions</h1>
    {#if description}<p class="admin-lede">{description}</p>{/if}
    </div>
    {#if actions}<div class="page-actions">{@render actions()}</div>{/if}
  </header>
  <GroupPermissionsTabs {activeTab} />
  {@render children()}
</section>

<style>
  .page-header { align-items: flex-start; display: flex; flex-wrap: wrap; gap: 24px; justify-content: space-between; margin-bottom: 32px; }
  .page-actions { flex-shrink: 0; }
  .admin-title { margin-bottom: 0; }
  .back-link { color: var(--admin-accent); display: inline-block; margin-bottom: 16px; }
  .permission-page :global(.permission-description) { color: var(--admin-muted); font-size: 13px; line-height: 1.55; margin: 0 0 18px; max-width: 640px; }
  .permission-page :global(.permission-block > h3) { color: var(--admin-muted); font-family: var(--admin-mono); font-size: 12px; font-weight: 500; letter-spacing: 0.5px; margin: 0 0 4px; text-transform: uppercase; }
  .permission-page :global(.permission-block > p) { color: var(--admin-muted); font-size: 13px; line-height: 1.55; margin: 0 0 12px; }
  .permission-page :global(.permission-save) { display: flex; flex-wrap: wrap; gap: 10px; justify-content: flex-end; margin-top: 24px; }
  .permission-page :global(.permission-notice) { margin: 0 0 20px; }
</style>
