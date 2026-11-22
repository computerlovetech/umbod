<script lang="ts">
  import NamespacePermissions from '#lib/components/admin/filesystem/NamespacePermissions.svelte';
  import { getGroupPermissionsWorkspace } from '#lib/components/admin/group-permissions/group-permissions-context.js';

  const workspace = getGroupPermissionsWorkspace();
</script>

<svelte:head><title>Shared namespaces · Permissions</title></svelte:head>

<NamespacePermissions state={workspace.namespaces} />
