<script lang="ts">
  import NamespacePermissions from '#lib/components/admin/filesystem/NamespacePermissions.svelte';
  import { getGroupPermissionsWorkspace } from '#lib/components/admin/group-permissions/group-permissions-context.js';

  const workspace = getGroupPermissionsWorkspace();
</script>

<svelte:head><title>Shared namespaces · Permissions</title></svelte:head>

{#if !workspace.busy && !workspace.dirty}
  <p class="namespace-link"><a href="/admin/namespaces">Manage shared namespaces</a></p>
{/if}
<NamespacePermissions state={workspace.namespaces} />

<style>
  .namespace-link { font-size: 0.875rem; margin: 0 0 1rem; text-align: end; }
  a { color: var(--admin-accent); }
</style>
