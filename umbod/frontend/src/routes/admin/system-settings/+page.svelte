<script lang="ts">
  import { page } from '$app/state';
  import { agentBehaviourApi } from '#lib/agent-behaviour/infrastructure/api.js';
  import { adminApi } from '#lib/admin/infrastructure/admin-api.js';
  import AdminShell from '#lib/components/admin/AdminShell.svelte';
  import SubpageContainer from '#lib/components/shared/workspace/SubpageContainer.svelte';
  import SystemSettingsContent from '#lib/components/admin/system-settings/SystemSettingsContent.svelte';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();
  const filesystemSettings = adminApi().filesystemSettings;
  const diagnosticsConfiguration = agentBehaviourApi().configuration;
</script>

<svelte:head><title>System settings · Administration</title></svelte:head>

<AdminShell activeItem="systemSettings" accountIdentity={data.accountIdentity} contentWidth="wide">
  <SubpageContainer title="System settings" lede="Manage policies that apply to everyone on this Umbod instance.">
    {#snippet actions()}<span class="scope">Instance-wide</span>{/snippet}
    {#if data.accountIdentity.kind === 'visible'}
      {#key data.accountIdentity.hiddenValues.id}
        <SystemSettingsContent query={page.url.searchParams} {filesystemSettings} {diagnosticsConfiguration} />
      {/key}
    {:else}
      <p class="admin-message admin-message--error" role="alert">Administration access is no longer available. Reload or sign in again.</p>
    {/if}
  </SubpageContainer>
</AdminShell>

<style>
  .scope { background: var(--admin-accent-soft); border: 1px solid var(--admin-border); border-radius: 999px; color: var(--admin-ink); display: inline-block; font-size: 12px; font-weight: 600; padding: 5px 10px; }
</style>
