<script lang="ts">
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import AdminOverviewDashboard from '$lib/components/admin/overview/AdminOverviewDashboard.svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();

  const fallbackAccountIdentity: HeaderAccountIdentityState = { kind: 'hidden' };
</script>

<svelte:head>
  <title>Admin overview</title>
</svelte:head>

<AdminShell activeItem="overview" accountIdentity={data.accountIdentity ?? fallbackAccountIdentity}>
  <AdminOverviewDashboard overview={data.overview} />
</AdminShell>
