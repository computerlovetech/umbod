<script lang="ts">
  import type { Snippet } from 'svelte';
  import GroupPermissionsTabs from './GroupPermissionsTabs.svelte';

  let { activeTab, description, backHref = null, children }: {
    activeTab: 'connectors' | 'filesystem';
    description: string;
    backHref?: string | null;
    children: Snippet;
  } = $props();
</script>

<section class="permission-page" aria-labelledby="group-permissions-title">
  <header class="page-header">
    {#if backHref !== null}
      <a class="back-link" href={backHref}>← Back to OpenAPI connector</a>
    {/if}
    <div class="page-heading">
      <div>
        <h1 id="group-permissions-title" class="admin-title">Group permissions</h1>
        <p class="admin-lede">{description}</p>
      </div>
      <a href="/admin/groups">Manage groups</a>
    </div>
  </header>
  <GroupPermissionsTabs {activeTab} />
  {@render children()}
</section>

<style>
  .page-header { margin-bottom: 32px; }
  .page-heading { align-items: flex-start; display: flex; gap: 24px; justify-content: space-between; }
  .page-heading > div { min-width: 0; }
  .page-heading > a { flex-shrink: 0; }
  .admin-title { margin-bottom: 0; }
  .back-link { color: var(--admin-accent); display: inline-block; margin-bottom: 16px; }
  .permission-page :global(.permission-description) { color: var(--admin-muted); font-size: 13px; line-height: 1.55; margin: 0 0 18px; max-width: 640px; }
  .permission-page :global(.permission-block > h3) { color: var(--admin-muted); font-family: var(--admin-mono); font-size: 12px; font-weight: 500; letter-spacing: 0.5px; margin: 0 0 4px; text-transform: uppercase; }
  .permission-page :global(.permission-block > p) { color: var(--admin-muted); font-size: 13px; line-height: 1.55; margin: 0 0 12px; }
  .permission-page :global(.permission-save) { display: flex; flex-wrap: wrap; gap: 10px; justify-content: flex-end; margin-top: 24px; }
  .permission-page :global(.permission-notice) { margin: 0 0 20px; }
  @media (max-width: 1000px) {
    .page-heading { flex-wrap: wrap; gap: 16px; }
  }
</style>
