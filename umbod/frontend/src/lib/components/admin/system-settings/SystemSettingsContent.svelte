<script lang="ts">
  import { beforeNavigate } from '$app/navigation';
  import { onMount, untrack } from 'svelte';
  import type { FilesystemSettingsAdministration } from '#lib/admin/system-settings/filesystem-settings-port.js';
  import type { ConfigurationPort } from '#lib/agent-behaviour/api.js';
  import { ConfigurationState } from '#lib/agent-behaviour/state/configuration-state.svelte.js';
  import ConfigurationEditor from '../agent-behaviour/ConfigurationEditor.svelte';
  import SystemSettingsWorkspace from './SystemSettingsWorkspace.svelte';
  import { FilesystemSettingsState } from './filesystem-settings-state.svelte';

  let { query, filesystemSettings, diagnosticsConfiguration }: {
    query: Pick<URLSearchParams, 'get'>;
    filesystemSettings: FilesystemSettingsAdministration;
    diagnosticsConfiguration: ConfigurationPort;
  } = $props();

  const filesystem = new FilesystemSettingsState(untrack(() => filesystemSettings));
  const configuration = new ConfigurationState(untrack(() => diagnosticsConfiguration));
  const section = $derived(query.get('section') === 'agent-diagnostics' ? 'agent-diagnostics' : 'filesystem');
  let diagnosticsStarted = false;

  $effect(() => {
    if (section !== 'agent-diagnostics' || diagnosticsStarted) return;
    diagnosticsStarted = true;
    untrack(() => { void configuration.load(); });
  });

  beforeNavigate(({ from, to, type, willUnload, shallow, cancel }): void => {
    if (shallow || (!willUnload && from?.route.id && from.route.id === to?.route.id)) return;
    if (!configuration.dirty) return;
    if (type === 'leave' || !window.confirm('Leave System settings and lose your unsaved reporting changes?')) cancel();
  });

  onMount(() => {
    void filesystem.load();
    return (): void => {
      filesystem.dispose();
      configuration.dispose();
    };
  });
</script>

<SystemSettingsWorkspace state={filesystem} {section} diagnosticsAllowed={configuration.allowed}>
  {#snippet diagnostics()}
    {#if configuration.allowed}
      <ConfigurationEditor state={configuration} section="reporting" />
    {:else}
      <p class="admin-message admin-message--error" role="alert">Administration access is no longer available. Reload or sign in again.</p>
    {/if}
  {/snippet}
</SystemSettingsWorkspace>
