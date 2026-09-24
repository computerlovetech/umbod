<script lang="ts">
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import InstanceConfigurationView from '$lib/components/admin/instance-configuration/InstanceConfigurationView.svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();
  const fallbackAccountIdentity: HeaderAccountIdentityState = { kind: 'hidden' };
</script>

<svelte:head><title>Configuration</title></svelte:head>

<AdminShell activeItem="instanceConfiguration" accountIdentity={data.accountIdentity ?? fallbackAccountIdentity}>
  <InstanceConfigurationView state={data} />
</AdminShell>
