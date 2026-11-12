<script lang="ts">
  import ConnectorsPage from '$lib/components/dashboard/ConnectorsPage.svelte';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();
</script>

<ConnectorsPage accountIdentity={data.accountIdentity} />
