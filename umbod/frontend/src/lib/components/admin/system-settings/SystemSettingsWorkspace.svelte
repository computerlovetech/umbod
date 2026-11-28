<script module lang="ts">
  export type SystemSettingsSection = 'filesystem' | 'provider-group-mappings' | 'agent-diagnostics' | 'portable-connectors';
</script>

<script lang="ts">
  import type { Snippet } from 'svelte';
  import { agentDiagnosticsReportingHref, portableConnectorSettingsHref, providerGroupMappingsHref, systemSettingsHref } from '#lib/workspace/navigation.js';
  import AdminSplitWorkspace from '../shared/AdminSplitWorkspace.svelte';
  import AdminSettingsActions from '../shared/AdminSettingsActions.svelte';
  import AdminToggleSetting from '../shared/AdminToggleSetting.svelte';
  import Button from '../shared/Button.svelte';
  import type { FilesystemSettingsState } from './filesystem-settings-state.svelte';
  import type { PortableConnectorSettingsState } from './portable-connector-settings-state.svelte';

  let { state, portableConnectors, section, diagnosticsAllowed, diagnostics, providerMappings }: {
    state: FilesystemSettingsState;
    portableConnectors: PortableConnectorSettingsState;
    section: SystemSettingsSection;
    diagnosticsAllowed: boolean;
    diagnostics: Snippet;
    providerMappings: Snippet;
  } = $props();
  const approvalLabel = 'Require approval for MCP file deletion';
  const detailLabels: Record<SystemSettingsSection, string> = {
    filesystem: 'Filesystem settings',
    'provider-group-mappings': 'Group mapping settings',
    'agent-diagnostics': 'Agent diagnostics settings',
    'portable-connectors': 'Portable connector settings'
  };
</script>

{#snippet folderIcon()}
  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M3 6h7l2 2h9v12H3z" /></svg>
{/snippet}

{#snippet diagnosticsIcon()}
  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l3-7 4 14 3-7h4" /></svg>
{/snippet}

{#snippet providerMappingsIcon()}
  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h7m-7 10h7m3-10 5 5-5 5m-3-5h8" /></svg>
{/snippet}

{#snippet portableConnectorsIcon()}
  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m8 6-6 6 6 6m8-12 6 6-6 6m-2-14-4 16" /></svg>
{/snippet}

{#snippet sectionLink(href: string, title: string, count: number, current: 'page' | 'location' | undefined, icon: Snippet)}
  <li>
    <a class="section-row" {href} aria-current={current}>
      <span class="section-marker">{@render icon()}</span>
      <span class="section-copy"><strong>{title}</strong><small>{count} {count === 1 ? 'setting' : 'settings'}</small></span>
    </a>
  </li>
{/snippet}

<AdminSplitWorkspace ariaLabel="System settings workspace" sidebarLabel="Settings sections" sidebarHeading="Settings sections" count={1 + Number(state.canNavigateToProtectedSettings) + Number(diagnosticsAllowed) + Number(portableConnectors.allowed)} detailLabel={detailLabels[section]}>
  {#snippet sidebar()}
    <nav aria-label="Available sections">
      <ul class="sections">
        {@render sectionLink(systemSettingsHref, 'Filesystem', 1, section === 'filesystem' ? 'page' : undefined, folderIcon)}
        {#if state.canNavigateToProtectedSettings}
          {@render sectionLink(providerGroupMappingsHref, 'Group mappings', 1, section === 'provider-group-mappings' ? 'location' : undefined, providerMappingsIcon)}
        {/if}
        {#if diagnosticsAllowed}
          {@render sectionLink(agentDiagnosticsReportingHref, 'Agent diagnostics', 2, section === 'agent-diagnostics' ? 'location' : undefined, diagnosticsIcon)}
        {/if}
        {#if portableConnectors.allowed}
          {@render sectionLink(portableConnectorSettingsHref, 'Portable connectors', 1, section === 'portable-connectors' ? 'location' : undefined, portableConnectorsIcon)}
        {/if}
      </ul>
    </nav>
  {/snippet}

  {#snippet detail()}
    {#if section === 'agent-diagnostics'}
      {@render detailHeader('Agent diagnostics', 'Controls for diagnostic reporting on this instance.', diagnosticsIcon)}
      {@render diagnostics()}
    {:else if section === 'provider-group-mappings'}
      {@render detailHeader('Group mappings', 'Provider values grant group access only through saved mappings.', providerMappingsIcon)}
      {@render providerMappings()}
    {:else if section === 'portable-connectors'}
      {@render detailHeader('Portable connectors', 'Instance-wide controls for portable connector drafts.', portableConnectorsIcon)}
      {@render portableConnectorSettings()}
    {:else}
      {@render detailHeader('Filesystem', 'Controls for file operations on this instance.', folderIcon)}
      {@render filesystem()}
    {/if}
  {/snippet}
</AdminSplitWorkspace>

{#snippet detailHeader(title: string, description: string, icon: Snippet)}
  <header class="detail-header">
    <span class="detail-icon">{@render icon()}</span>
    <div>
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
  </header>
{/snippet}

{#snippet filesystem()}

    {#if state.loading}
      <p role="status">Loading filesystem settings…</p>
    {/if}
    {#if state.failure}
      <p class="notice" role="alert">{state.failure}</p>
    {/if}
    {#if state.canRetry}
      <Button variant="secondary" onclick={state.load}>Try again</Button>
    {/if}

    {#if state.ready}
      <AdminToggleSetting title={approvalLabel} description="Ask for human confirmation before an MCP tool deletes a file. Turning this off doesn’t grant delete permission or change the browser’s confirmation dialog." checked={state.checked} disabled={state.busy || state.resetting} onChange={(checked): void => state.change(checked)} children={state.resetting || !state.checked ? approvalDetails : undefined}>
        {#snippet metadata()}
          <div class="source-line">
            <span class="source">{state.sourceLabel}</span>
            {#if state.canReset}
              <Button variant="quiet" size="compact" disabled={state.busy} onclick={state.reset}>Reset to default</Button>
            {/if}
          </div>
        {/snippet}
      </AdminToggleSetting>
      <AdminSettingsActions busy={state.busy} dirty={state.dirty} onDiscard={state.discard} onSave={state.save} />
    {/if}
{/snippet}

{#snippet portableConnectorSettings()}
  {#if portableConnectors.loading}
    <p role="status">Loading portable connector settings…</p>
  {/if}
  {#if portableConnectors.failure}
    <p class="notice" role="alert">{portableConnectors.failure}</p>
  {/if}
  {#if portableConnectors.canRetry}
    <Button variant="secondary" onclick={portableConnectors.load}>Try again</Button>
  {/if}
  {#if portableConnectors.ready}
    <AdminToggleSetting title="Enable portable connectors" description="Let authenticated MCP authors create, revise, and validate their own drafts. Drafts are not published or run as tools." checked={portableConnectors.checked} disabled={portableConnectors.busy} onChange={portableConnectors.change} />
    <AdminSettingsActions busy={portableConnectors.busy} dirty={portableConnectors.dirty} onDiscard={portableConnectors.discard} onSave={portableConnectors.save} />
  {/if}
{/snippet}

{#snippet approvalDetails()}
  {#if state.resetting}
    <p role="status">Save changes to restore the instance default. The current value is shown until then.</p>
  {/if}
  {#if !state.checked}
    <p class="notice">With approval off, new MCP file deletion requests won’t ask for confirmation. Approvals already in progress still need a response.</p>
  {/if}
{/snippet}

<style>
  .sections { list-style: none; margin: 0; padding: 0; }
  .section-row { align-items: flex-start; border-top: 1px solid var(--admin-border); color: inherit; display: flex; gap: 0.6rem; padding: 15px 16px; text-decoration: none; }
  .section-row:hover, .section-row[aria-current] { background: var(--admin-accent-soft); }
  .section-row[aria-current] { box-shadow: inset 2px 0 0 var(--admin-accent); }
  .section-row:focus-visible { outline-offset: -3px; }
  .section-marker { align-items: center; color: var(--admin-accent); display: inline-flex; flex: 0 0 20px; height: 20px; justify-content: center; }
  .section-copy { display: grid; font-size: 13px; gap: 0.25rem; }
  .section-copy strong { font-weight: 600; }
  .section-copy small { color: var(--admin-muted); font-size: 11px; }
  .detail-icon { align-items: center; background: var(--admin-action); border-radius: 50%; color: var(--admin-panel); display: inline-flex; flex: 0 0 36px; height: 36px; justify-content: center; }
  .detail-header { align-items: center; display: flex; gap: 0.75rem; margin-bottom: 24px; }
  h2 { font-size: 20px; margin: 0; }
  p { color: var(--admin-muted); font-size: 13px; line-height: 1.5; margin: 0; }
  .detail-header p { margin-top: 0.375rem; }
  .source-line { align-items: center; display: flex; flex-wrap: wrap; gap: 0.5rem; }
  .source { background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: 999px; color: var(--admin-muted); font-size: 11px; padding: 3px 8px; }
  .notice { background: var(--admin-warning-bg); border: 1px solid var(--admin-warning-border); border-radius: var(--admin-radius); color: var(--admin-warning-text); padding: 10px 12px; }
  .notice[role='alert'] { margin-bottom: 1rem; }
</style>
