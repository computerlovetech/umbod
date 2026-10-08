<script lang="ts">
  import { page } from '$app/state';
  import { operationState } from '$lib/admin/operations/operation-state.svelte';
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import GroupPermissionsManager from '$lib/components/admin/group-permissions/GroupPermissionsManager.svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import type { GroupPermissionsPageData, SaveGroupPermissionsResult } from '$lib/admin/group-permissions';

  type AdminGroupPermissionsPageData = GroupPermissionsPageData & {
    accountIdentity?: HeaderAccountIdentityState;
  };

  let { data }: { data: AdminGroupPermissionsPageData; form?: SaveGroupPermissionsResult } = $props();
  const form = $derived(operationState.forOwner({ route: page.url.pathname }) as SaveGroupPermissionsResult);

  const fallbackAccountIdentity: HeaderAccountIdentityState = { kind: 'hidden' };
</script>

<svelte:head>
  <title>Group permissions</title>
</svelte:head>

<AdminShell activeItem="groupPermissions" accountIdentity={data.accountIdentity ?? fallbackAccountIdentity} contentWidth="wide">
  <div class="admin-page">
    <GroupPermissionsManager data={data} {form} />
  </div>
</AdminShell>
