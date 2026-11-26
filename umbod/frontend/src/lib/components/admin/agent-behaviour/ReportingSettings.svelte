<script lang="ts">
  import type { ConfigurationState } from '#lib/agent-behaviour/state/configuration-state.svelte.js';
  import AdminToggle from '#lib/components/admin/shared/AdminToggle.svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import Select from '#lib/components/admin/shared/Select.svelte';
  import TextAreaField from '#lib/components/shared/TextAreaField.svelte';
  import { agentDiagnosticsHref } from '#lib/workspace/navigation.js';
  import { ReportingInstructionsState } from './reporting-instructions-state.svelte';

  let { state }: { state: ConfigurationState } = $props();
  const instructions = new ReportingInstructionsState();
  const pageId = $props.id();
  const reportingModes = [
    { value: 'requested', label: 'When requested' },
    { value: 'proactive', label: 'Allow proactive reports' }
  ];

  function changeAcceptance(id: string, event: Event): void {
    if (event.currentTarget instanceof HTMLInputElement) state.updateSettings(id, 'enabled', event.currentTarget.checked);
  }
</script>

<section aria-labelledby="reporting-settings-title">
  <header>
    <h2 id="reporting-settings-title">Reporting settings</h2>
    <p>Manage which diagnostic reports Umbod accepts. These settings do not hide the MCP reporting tool.</p>
  </header>
  <div class="settings-list">
    {#each state.settings as setting (setting.id)}
      {@const nameSuffix = state.settings.length > 1 ? ` · ${setting.name}` : ''}
      {@const instructionsLabel = `Collection instructions${nameSuffix}`}
      {@const instructionsId = `${pageId}-${setting.id}-instructions`}
      {@const editing = instructions.isOpen(setting.id)}
      {@const editLabel = editing ? 'Close editor' : 'Edit instructions'}
      <section class="setting-group" aria-label={state.settings.length > 1 ? setting.name : 'Diagnostic reporting'}>
        {#if state.settings.length > 1}<p class="profile-name">{setting.name}</p>{/if}
        <div class="card">
          <div class="setting-row">
            <div>
              <h3>Accept diagnostic reports</h3>
              <p>Choose whether Umbod accepts new reports.</p>
            </div>
            <div class="toggle">
              <AdminToggle checked={setting.enabled} ariaLabel={`Accept diagnostic reports${nameSuffix}`} disabled={state.busy} onchange={(event): void => changeAcceptance(setting.id, event)} />
              <span aria-hidden="true">{setting.enabled ? 'On' : 'Off'}</span>
            </div>
          </div>
          {#if setting.enabled}
            <div class="mode-row">
              <Select label="Reporting mode" accessibleName={`Reporting mode${nameSuffix}`} options={reportingModes} value={setting.allow_proactive ? 'proactive' : 'requested'} disabled={state.busy} compact inline onchange={(value): void => state.updateSettings(setting.id, 'allow_proactive', value === 'proactive')} />
              {#if setting.allow_proactive}
                <p class="mode-help">Proactive reports still require permission from the user and client.</p>
              {/if}
            </div>
          {/if}
        </div>
        <div class="card instructions-card">
          <div class="setting-row">
            <div class="instructions-copy">
              <h3>Collection instructions</h3>
              {#if !editing}<p class="instructions-preview">{setting.collection_instructions || 'No collection instructions.'}</p>{/if}
            </div>
            <Button variant="quiet" size="compact" aria-label={`${editLabel}${nameSuffix}`} aria-expanded={editing} aria-controls={`${instructionsId}-editor`} onclick={(): void => instructions.toggle(setting.id)}>
              {editLabel}
            </Button>
          </div>
          <div class="instructions-editor" id={`${instructionsId}-editor`} hidden={!editing}>
            {#if editing}
              <TextAreaField id={instructionsId} label={instructionsLabel} value={setting.collection_instructions} disabled={state.busy} rows={6} maxlength={8000} oninput={(event): void => state.updateSettings(setting.id, 'collection_instructions', event.currentTarget.value)} />
            {/if}
          </div>
        </div>
      </section>
    {:else}
      <p>No reporting settings configured.</p>
    {/each}
  </div>
  <footer>
    <div role="status" aria-atomic="true">
      <p><strong>Saved mode:</strong> {state.savedReportingMode}</p>
      {#if !state.conflict && state.reportingMode !== state.savedReportingMode}
        <p><strong>After saving:</strong> {state.reportingMode}</p>
      {/if}
      {#if state.reportingNeedsEnabledPattern}
        <p>Reporting requires an enabled pattern in an enabled reporting setting.</p>
      {/if}
    </div>
    <div class="pattern-status">
      <p>{state.enabledPatternCount} enabled {state.enabledPatternCount === 1 ? 'pattern' : 'patterns'}</p>
      <a class="admin-back-link" href={agentDiagnosticsHref}>Manage patterns <span aria-hidden="true">→</span></a>
    </div>
  </footer>
</section>

<style>
  h2, h3, p { margin: 0; }
  h2 { font-size: 20px; }
  h3, .profile-name { font-size: 15px; }
  .profile-name { color: var(--admin-ink); font-weight: 600; }
  p { color: var(--admin-muted); font-size: 13px; line-height: 1.5; }
  header p, .setting-row p { margin-top: .375rem; }
  .settings-list { display: grid; gap: 1.25rem; margin-top: 1rem; }
  .setting-group { display: grid; gap: .65rem; min-width: 0; }
  .card { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 16px; min-width: 0; }
  .setting-row, footer { display: flex; align-items: center; justify-content: space-between; gap: .65rem 1rem; flex-wrap: wrap; }
  .toggle { display: flex; flex-shrink: 0; align-items: center; gap: .5rem; font-size: 13px; }
  .mode-row { border-top: 1px solid var(--admin-border); margin-top: .8rem; padding-top: .8rem; }
  .mode-help { margin-top: .375rem; }
  .instructions-card { background: var(--admin-soft); }
  .instructions-copy { flex: 1 1 14rem; min-width: 0; }
  .instructions-preview { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow: hidden; overflow-wrap: anywhere; }
  .instructions-editor:not([hidden]) { margin-top: .65rem; }
  footer { margin-top: .8rem; align-items: flex-start; }
  footer strong { color: var(--admin-ink); }
  .pattern-status { display: flex; align-items: baseline; flex-wrap: wrap; gap: .15rem .6rem; }
  .pattern-status a { margin-bottom: 0; gap: .3rem; }
</style>
