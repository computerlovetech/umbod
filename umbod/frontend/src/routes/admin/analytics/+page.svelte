<script lang="ts">
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import AnalyticsWorkspace from '$lib/components/admin/analytics/AnalyticsWorkspace.svelte';
  import { AnalyticsState } from '$lib/admin/analytics/analytics-state.svelte';
  import { adminApi } from '$lib/admin/infrastructure/admin-api';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();
  const state = new AnalyticsState(adminApi().analytics);
</script>

<svelte:head><title>Log analytics · Administration</title></svelte:head>
<AdminShell activeItem="analytics" accountIdentity={data.accountIdentity ?? { kind: 'hidden' }} contentWidth="wide">
  <div class="admin-page"><AnalyticsWorkspace {state} /></div>
</AdminShell>
