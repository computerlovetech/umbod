<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { adminApi } from '#lib/admin/infrastructure/admin-api.js';
  import AdminShell from '#lib/components/admin/AdminShell.svelte';
  import AddNamespaceButton from '#lib/components/admin/filesystem/AddNamespaceButton.svelte';
  import NamespaceManagement from '#lib/components/admin/filesystem/NamespaceManagement.svelte';
  import { NamespaceManagementState } from '#lib/components/admin/filesystem/namespace-management-state.svelte.js';
  import SubpageContainer from '#lib/components/shared/workspace/SubpageContainer.svelte';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();
  const state = new NamespaceManagementState(adminApi().namespaces, (): null => null);

  $effect.pre(() => {
    const identity = data.accountIdentity ?? { kind: 'hidden' as const };
    untrack(() => state.observeAccountIdentity(identity));
  });

  onMount(() => {
    void state.ensureLoaded();
    return state.dispose;
  });
</script>

<svelte:head><title>Shared namespaces · Administration</title></svelte:head>

<AdminShell activeItem="namespaces" accountIdentity={data.accountIdentity ?? { kind: 'hidden' }} contentWidth="wide">
  <SubpageContainer title="Shared namespaces" lede="Manage shared storage used by your groups.">
    {#snippet actions()}<AddNamespaceButton {state} />{/snippet}
    <NamespaceManagement {state} />
  </SubpageContainer>
</AdminShell>
