<script lang="ts">
  import FilesystemAccessEditor from '$lib/components/admin/filesystem/FilesystemAccessEditor.svelte';
  import { getGroupPermissionsWorkspace } from '$lib/components/admin/group-permissions/group-permissions-context';

  const workspace = getGroupPermissionsWorkspace();
</script>

<svelte:head><title>Filesystem · Group permissions</title></svelte:head>

<FilesystemAccessEditor state={workspace.filesystem} editor={workspace.filesystemEditor} />
