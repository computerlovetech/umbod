<script lang="ts">
  import GettingStarted from '$lib/components/getting-started/GettingStarted.svelte';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();
</script>

<GettingStarted activePage="telemetry" installerBaseUrl={data.installerBaseUrl} />
