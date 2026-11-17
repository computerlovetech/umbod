<script lang="ts">
  import NamespaceManagement from '#lib/components/admin/filesystem/NamespaceManagement.svelte';
  import { getGroupPermissionsWorkspace } from '#lib/components/admin/group-permissions/group-permissions-context.js';

  const workspace = getGroupPermissionsWorkspace();
</script>

<svelte:head><title>Shared namespaces · Group permissions</title></svelte:head>

<NamespaceManagement state={workspace.namespaces} />
