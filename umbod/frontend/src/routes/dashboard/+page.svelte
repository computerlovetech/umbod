<script lang="ts">
  import Dashboard from '$lib/components/dashboard/Dashboard.svelte';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();
</script>

<Dashboard mcpEndpoint={data.mcpEndpoint} accountIdentity={data.accountIdentity} />
