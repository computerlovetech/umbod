<script lang="ts">
  import FilesystemAccessPage from '$lib/components/admin/filesystem/FilesystemAccessPage.svelte';
  import type { PageData } from './$types';
  let { data }: { data: PageData } = $props();
</script>

<svelte:head><title>Filesystem · Group permissions</title></svelte:head>
<FilesystemAccessPage accountIdentity={data.accountIdentity ?? { kind: 'hidden' }} />
