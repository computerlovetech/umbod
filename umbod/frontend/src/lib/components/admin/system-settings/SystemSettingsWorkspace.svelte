<script lang="ts">
  import type { Snippet } from 'svelte';
  import { agentDiagnosticsReportingHref, systemSettingsHref } from '#lib/workspace/navigation.js';
  import AdminSplitWorkspace from '../shared/AdminSplitWorkspace.svelte';
  import AdminToggle from '../shared/AdminToggle.svelte';
  import Button from '../shared/Button.svelte';
  import type { FilesystemSettingsState } from './filesystem-settings-state.svelte';

  let { state, section, diagnosticsAllowed, diagnostics }: {
    state: FilesystemSettingsState;
    section: 'filesystem' | 'agent-diagnostics';
    diagnosticsAllowed: boolean;
    diagnostics: Snippet;
  } = $props();
  const approvalLabel = 'Require approval for MCP file deletion';

  function changeApproval(event: Event): void {
    if (event.currentTarget instanceof HTMLInputElement) state.change(event.currentTarget.checked);
  }
</script>

{#snippet folderIcon()}
  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M3 6h7l2 2h9v12H3z" /></svg>
{/snippet}

{#snippet diagnosticsIcon()}
  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l3-7 4 14 3-7h4" /></svg>
{/snippet}

<AdminSplitWorkspace ariaLabel="System settings workspace" sidebarLabel="Settings sections" sidebarHeading="Settings sections" count={diagnosticsAllowed ? 2 : 1} detailLabel={section === 'agent-diagnostics' ? 'Agent diagnostics settings' : 'Filesystem settings'}>
  {#snippet sidebar()}
    <nav aria-label="Available sections">
      <ul class="sections">
        <li>
          <a class="section-row" href={systemSettingsHref} aria-current={section === 'filesystem' ? 'page' : undefined}>
            <span class="section-marker">{@render folderIcon()}</span>
            <span class="section-copy"><strong>Filesystem</strong><small>1 setting</small></span>
          </a>
        </li>
        {#if diagnosticsAllowed}
          <li>
            <a class="section-row" href={agentDiagnosticsReportingHref} aria-current={section === 'agent-diagnostics' ? 'location' : undefined}>
              <span class="section-marker">{@render diagnosticsIcon()}</span>
              <span class="section-copy"><strong>Agent diagnostics</strong><small>Reporting settings</small></span>
            </a>
          </li>
        {/if}
      </ul>
    </nav>
  {/snippet}

  {#snippet detail()}
    {#if section === 'agent-diagnostics'}
      {@render diagnostics()}
    {:else}
      {@render filesystem()}
    {/if}
  {/snippet}
</AdminSplitWorkspace>

{#snippet filesystem()}
    <header class="detail-header">
      <span class="folder-icon">{@render folderIcon()}</span>
      <div>
        <h2>Filesystem</h2>
        <p>Controls for file operations on this instance.</p>
      </div>
    </header>

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
      <div class="setting">
        <div class="setting-row">
          <div>
            <h3>{approvalLabel}</h3>
            <p>Ask for human confirmation before an MCP tool deletes a file. Turning this off doesn’t grant delete permission or change the browser’s confirmation dialog.</p>
            <div class="source-line">
              <span class="source">{state.sourceLabel}</span>
              {#if state.canReset}
                <Button variant="quiet" size="compact" disabled={state.busy} onclick={state.reset}>Reset to default</Button>
              {/if}
            </div>
          </div>
          <div class="toggle">
            <AdminToggle checked={state.checked} disabled={state.busy || state.resetting} ariaLabel={approvalLabel} onchange={changeApproval} />
            <span aria-hidden="true">{state.checked ? 'On' : 'Off'}</span>
          </div>
        </div>
        {#if state.resetting}
          <p role="status">Save changes to restore the instance default. The current value is shown until then.</p>
        {/if}
        {#if !state.checked}
          <p class="notice">With approval off, new MCP file deletion requests won’t ask for confirmation. Approvals already in progress still need a response.</p>
        {/if}
      </div>

      <div class="actions">
        <p role="status">{state.busy ? 'Saving changes…' : state.dirty ? 'Unsaved changes' : 'No unsaved changes'}</p>
        <div class="buttons">
          {#if state.dirty}
            <Button variant="secondary" disabled={state.busy} onclick={state.discard}>Discard</Button>
          {/if}
          <Button disabled={!state.dirty || state.busy} onclick={state.save}>Save changes</Button>
        </div>
      </div>
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
  .folder-icon { align-items: center; background: var(--admin-action); border-radius: 50%; color: var(--admin-panel); display: inline-flex; flex: 0 0 auto; height: 20px; justify-content: center; width: 20px; }
  .detail-header { align-items: center; display: flex; gap: 0.75rem; margin-bottom: 24px; }
  .detail-header .folder-icon { height: 36px; width: 36px; }
  h2, h3, p { margin: 0; }
  h2 { font-size: 20px; }
  h3 { font-size: 15px; }
  p { color: var(--admin-muted); font-size: 13px; line-height: 1.5; margin-top: 0.375rem; }
  .setting { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 16px; }
  .setting-row, .actions { align-items: flex-start; display: flex; gap: 1rem; justify-content: space-between; }
  .source-line, .toggle, .buttons { align-items: center; display: flex; flex-wrap: wrap; gap: 0.5rem; }
  .source-line { margin-top: 0.875rem; }
  .source { background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: 999px; color: var(--admin-muted); font-size: 11px; padding: 3px 8px; }
  .toggle { flex-shrink: 0; font-size: 13px; }
  .notice { background: var(--admin-warning-bg); border: 1px solid var(--admin-warning-border); border-radius: var(--admin-radius); color: var(--admin-warning-text); padding: 10px 12px; }
  .setting .notice { margin-top: 1rem; }
  .notice[role='alert'] { margin-bottom: 1rem; }
  .actions { align-items: center; flex-wrap: wrap; margin-top: 1rem; }
</style>
