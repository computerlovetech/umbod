<script lang="ts">
  import FilesPage from '$lib/components/files/FilesPage.svelte';
  import type { PageData } from './$types';
  let { data }: { data: PageData } = $props();
</script>

<FilesPage accountIdentity={data.accountIdentity} />
