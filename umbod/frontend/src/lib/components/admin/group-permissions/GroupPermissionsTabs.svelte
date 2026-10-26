<script lang="ts">
  let { activeTab }: { activeTab: 'connectors' | 'filesystem' } = $props();

  const tabs = [
    { id: 'connectors', label: 'Connectors', href: '/admin/group-permissions/connectors' },
    { id: 'filesystem', label: 'Filesystem', href: '/admin/group-permissions/filesystem' }
  ] as const;
</script>

<nav class="permission-tabs" aria-label="Group permission type">
  {#each tabs as tab (tab.id)}
    <a class={['permission-tab', { active: activeTab === tab.id }]} href={tab.href} aria-current={activeTab === tab.id ? 'page' : undefined}>{tab.label}</a>
  {/each}
</nav>

<style>
  .permission-tabs { border-bottom: 1px solid var(--admin-border); display: flex; flex-wrap: wrap; gap: 12px 24px; margin-bottom: 32px; }
  .permission-tab { border-bottom: 2px solid transparent; color: var(--admin-muted); font-size: 14px; font-weight: 600; margin-bottom: -1px; padding: 0 2px 10px; text-decoration: none; }
  .permission-tab:hover { color: var(--admin-ink); }
  .permission-tab.active { border-bottom-color: var(--admin-accent); color: var(--admin-accent); }
  .permission-tab:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: 3px; }
</style>
