<script lang="ts">
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import FilesystemAccessPage from '$lib/components/admin/filesystem/FilesystemAccessPage.svelte';
  import type { PageData } from './$types';
  let { data }: { data: PageData } = $props();
</script>

<svelte:head><title>Filesystem · Group permissions</title></svelte:head>
<AdminShell activeItem="groupPermissions" accountIdentity={data.accountIdentity ?? { kind: 'hidden' }} contentWidth="wide">
  <FilesystemAccessPage />
</AdminShell>
