<script lang="ts">
  import { onMount } from 'svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import { adminApi } from '$lib/admin/infrastructure/admin-api';
  import FilesystemAccessEditor from './FilesystemAccessEditor.svelte';
  import { FilesystemAccessState } from './filesystem-access-state.svelte';
  let { accountIdentity }: { accountIdentity: HeaderAccountIdentityState } = $props();
  const api = adminApi();
  const state = new FilesystemAccessState(api.filesystem, api.groups);
  onMount(() => { void state.load(); return state.dispose; });
</script>

<AdminShell activeItem="groupPermissions" {accountIdentity} contentWidth="wide" contentLoading={state.loading}>
  <FilesystemAccessEditor {state} />
</AdminShell>
