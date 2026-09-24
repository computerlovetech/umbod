<script lang="ts">
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import GroupPermissionsManager from '$lib/components/admin/group-permissions/GroupPermissionsManager.svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import type { GroupPermissionsPageData, SaveGroupPermissionsResult } from './+page.server';

  type AdminGroupPermissionsPageData = GroupPermissionsPageData & {
    accountIdentity?: HeaderAccountIdentityState;
  };

  let { data, form }: { data: AdminGroupPermissionsPageData; form?: SaveGroupPermissionsResult } = $props();

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
