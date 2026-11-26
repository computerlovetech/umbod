<script lang="ts">
  import { onMount } from 'svelte';
  import { adminApi } from '#lib/admin/infrastructure/admin-api.js';
  import AdminShell from '#lib/components/admin/AdminShell.svelte';
  import SubpageContainer from '#lib/components/shared/workspace/SubpageContainer.svelte';
  import SystemSettingsWorkspace from '#lib/components/admin/system-settings/SystemSettingsWorkspace.svelte';
  import { FilesystemSettingsState } from '#lib/components/admin/system-settings/filesystem-settings-state.svelte.js';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();
  const state = new FilesystemSettingsState(adminApi().filesystemSettings);

  onMount(() => {
    void state.load();
    return state.dispose;
  });
</script>

<svelte:head><title>System settings · Administration</title></svelte:head>

<AdminShell activeItem="systemSettings" accountIdentity={data.accountIdentity} contentWidth="wide">
  <SubpageContainer title="System settings" lede="Manage policies that apply to everyone on this Umbod instance.">
    {#snippet actions()}<span class="scope">Instance-wide</span>{/snippet}
    <SystemSettingsWorkspace {state} />
  </SubpageContainer>
</AdminShell>

<style>
  .scope { background: var(--admin-accent-soft); border: 1px solid var(--admin-border); border-radius: 999px; color: var(--admin-ink); display: inline-block; font-size: 12px; font-weight: 600; padding: 5px 10px; }
</style>
