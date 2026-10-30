<script lang="ts">
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import GroupsWorkspace from '$lib/components/admin/groups/GroupsWorkspace.svelte';
  import type { PageData } from './$types';
  let { data }: { data: PageData } = $props();
</script>

<svelte:head><title>Groups · Administration</title></svelte:head>
<AdminShell activeItem="groups" accountIdentity={data.accountIdentity ?? { kind: 'hidden' }} contentWidth="wide">
  <div class="admin-page">{#key data.groups}<GroupsWorkspace groups={data.groups} />{/key}</div>
</AdminShell>
