<script lang="ts">
  import { beforeNavigate } from '$app/navigation';
  import { onMount, untrack } from 'svelte';
  import type { GroupCatalogue } from '#lib/admin/groups/port.js';
  import type { ProviderGroupMappingsAdministration } from '#lib/admin/system-settings/provider-group-mappings-port.js';
  import type { FilesystemSettingsAdministration } from '#lib/admin/system-settings/filesystem-settings-port.js';
  import type { ConfigurationPort } from '#lib/agent-behaviour/api.js';
  import { ConfigurationState } from '#lib/agent-behaviour/state/configuration-state.svelte.js';
  import ConfigurationEditor from '../agent-behaviour/ConfigurationEditor.svelte';
  import ProviderGroupMappingsEditor from './ProviderGroupMappingsEditor.svelte';
  import SystemSettingsWorkspace, { type SystemSettingsSection } from './SystemSettingsWorkspace.svelte';
  import { FilesystemSettingsState } from './filesystem-settings-state.svelte';
  import { ProviderGroupMappingsState } from './provider-group-mappings-state.svelte';

  let { query, filesystemSettings, providerGroupMappings, groups, diagnosticsConfiguration }: {
    query: Pick<URLSearchParams, 'get'>;
    filesystemSettings: FilesystemSettingsAdministration;
    providerGroupMappings: ProviderGroupMappingsAdministration;
    groups: Pick<GroupCatalogue, 'list'>;
    diagnosticsConfiguration: ConfigurationPort;
  } = $props();

  const filesystem = new FilesystemSettingsState(untrack(() => filesystemSettings));
  const mappings = untrack(() => new ProviderGroupMappingsState(providerGroupMappings, groups));
  const configuration = new ConfigurationState(untrack(() => diagnosticsConfiguration));
  const section = $derived.by((): SystemSettingsSection => {
    const requested = query.get('section');
    return requested === 'agent-diagnostics' || requested === 'provider-group-mappings' ? requested : 'filesystem';
  });
  let diagnosticsStarted = false;

  $effect(() => {
    if (section !== 'agent-diagnostics' || diagnosticsStarted) return;
    diagnosticsStarted = true;
    untrack(() => { void configuration.load(); });
  });

  $effect(() => {
    if (section === 'provider-group-mappings') untrack(mappings.start);
  });

  beforeNavigate(({ from, to, type, willUnload, shallow, cancel }): void => {
    if (shallow || (!willUnload && from?.route.id && from.route.id === to?.route.id)) return;
    if (!configuration.dirty && !mappings.dirty) return;
    const message = mappings.dirty
      ? 'Leave System settings and lose your unsaved changes?'
      : 'Leave System settings and lose your unsaved reporting changes?';
    if (type === 'leave' || !window.confirm(message)) cancel();
  });

  onMount(() => {
    void filesystem.load();
    return (): void => {
      filesystem.dispose();
      mappings.dispose();
      configuration.dispose();
    };
  });
</script>

<SystemSettingsWorkspace state={filesystem} {section} diagnosticsAllowed={configuration.allowed}>
  {#snippet providerMappings()}
    <ProviderGroupMappingsEditor state={mappings} />
  {/snippet}
  {#snippet diagnostics()}
    {#if configuration.allowed}
      <ConfigurationEditor state={configuration} section="reporting" />
    {:else}
      <p class="admin-message admin-message--error" role="alert">Administration access is no longer available. Reload or sign in again.</p>
    {/if}
  {/snippet}
</SystemSettingsWorkspace>
