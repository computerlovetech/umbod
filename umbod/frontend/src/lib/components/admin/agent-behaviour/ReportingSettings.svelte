<script lang="ts">
  import { tick } from 'svelte';
  import type { ConfigurationState } from '#lib/agent-behaviour/state/configuration-state.svelte.js';
  import AdminToggleSetting from '#lib/components/admin/shared/AdminToggleSetting.svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import TextAreaField from '#lib/components/shared/TextAreaField.svelte';
  import { agentDiagnosticsHref } from '#lib/workspace/navigation.js';
  import { ReportingInstructionsState } from './reporting-instructions-state.svelte';

  let { state }: { state: ConfigurationState } = $props();
  const instructions = new ReportingInstructionsState();
  const pageId = $props.id();

  async function changeInclusion(id: string, included: boolean, editButtonId: string, button: HTMLButtonElement): Promise<void> {
    state.setPlaybookIncluded(id, included);
    await tick();
    if (!button.isConnected) button.ownerDocument.getElementById(editButtonId)?.focus();
  }
</script>

<section aria-label="Reporting settings">
  <div class="settings-list">
    <AdminToggleSetting title="Enable diagnostic reporting" description="Let agents submit diagnostic reports through MCP. Turning this off keeps your instructions, patterns, and past reports." checked={state.reportingEnabled} disabled={state.busy} onChange={state.setReportingEnabled}>
      {#snippet metadata()}
        <div class="reporting-status" role="status" aria-atomic="true">
          <p><strong>Saved:</strong> {state.savedReportingEnabled ? 'On' : 'Off'}</p>
          {#if state.reportingEnabled !== state.savedReportingEnabled}
            <p><strong>Draft:</strong> {state.reportingEnabled ? 'On' : 'Off'}</p>
          {/if}
          {#if state.savedReportingNeedsUsablePlaybook}
            <p>No usable playbook in the saved configuration.</p>
          {/if}
          {#if state.reportingNeedsUsablePlaybook && !state.savedReportingNeedsUsablePlaybook}
            <p>No usable playbook after saving. Reporting requires an included playbook with at least one enabled pattern.</p>
          {/if}
        </div>
      {/snippet}
    </AdminToggleSetting>
    {#each state.settings as setting (setting.id)}
      {@const nameSuffix = state.settings.length > 1 ? ` · ${setting.name}` : ''}
      {@const instructionsLabel = `Collection instructions${nameSuffix}`}
      {@const instructionsId = `${pageId}-${setting.id}-instructions`}
      {@const editing = instructions.isOpen(setting.id)}
      {@const editLabel = editing ? 'Close editor' : 'Edit instructions'}
      {@const editButtonId = `${instructionsId}-edit`}
      {@const inclusionLabel = setting.enabled ? 'Exclude playbook' : 'Include playbook'}
      <section class="setting-group" aria-label={state.settings.length > 1 ? setting.name : 'Collection instructions'}>
        {#if state.settings.length > 1}<p class="profile-name">{setting.name}</p>{/if}
        <div class="card instructions-card">
          <div class="setting-row">
            <div class="instructions-copy">
              <h3>Collection instructions</h3>
              {#if !editing}<p class="instructions-preview">{setting.collection_instructions || 'No collection instructions.'}</p>{/if}
            </div>
            <div class="instructions-actions">
              {#if state.canEditPlaybookInclusion(setting)}
                <Button variant="quiet" size="compact" aria-label={`${inclusionLabel}${nameSuffix}`} disabled={state.busy} onclick={(event): Promise<void> => changeInclusion(setting.id, !setting.enabled, editButtonId, event.currentTarget)}>
                  {inclusionLabel}
                </Button>
              {/if}
              <Button id={editButtonId} variant="quiet" size="compact" aria-label={`${editLabel}${nameSuffix}`} aria-expanded={editing} aria-controls={`${instructionsId}-editor`} onclick={(): void => instructions.toggle(setting.id)}>
                {editLabel}
              </Button>
            </div>
          </div>
          <div class="instructions-editor" id={`${instructionsId}-editor`} hidden={!editing}>
            {#if editing}
              <TextAreaField id={instructionsId} label={instructionsLabel} value={setting.collection_instructions} disabled={state.busy} rows={6} maxlength={8000} oninput={(event): void => state.updateCollectionInstructions(setting.id, event.currentTarget.value)} />
            {/if}
          </div>
        </div>
      </section>
    {:else}
      <p>No reporting settings configured.</p>
    {/each}
  </div>
  <div class="pattern-status">
    <p>{state.enabledPatternCount} enabled {state.enabledPatternCount === 1 ? 'pattern' : 'patterns'}</p>
    <a class="admin-back-link" href={agentDiagnosticsHref}>Manage patterns <span aria-hidden="true">→</span></a>
  </div>
</section>

<style>
  h3, p { margin: 0; }
  h3, .profile-name { font-size: 15px; }
  .profile-name { color: var(--admin-ink); font-weight: 600; }
  p { color: var(--admin-muted); font-size: 13px; line-height: 1.5; }
  .setting-row p { margin-top: .375rem; }
  .settings-list { display: grid; gap: 1rem; }
  .setting-group { display: grid; gap: .65rem; min-width: 0; }
  .card { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 16px; min-width: 0; }
  .setting-row { display: flex; align-items: center; justify-content: space-between; gap: .65rem 1rem; flex-wrap: wrap; }
  .instructions-card { background: var(--admin-soft); }
  .instructions-actions { display: flex; flex-wrap: wrap; gap: .4rem; }
  .instructions-copy { flex: 1 1 14rem; min-width: 0; }
  .instructions-preview { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow: hidden; overflow-wrap: anywhere; }
  .instructions-editor:not([hidden]) { margin-top: .65rem; }
  .reporting-status strong { color: var(--admin-ink); }
  .pattern-status { display: flex; align-items: baseline; flex-wrap: wrap; gap: .15rem .6rem; justify-content: flex-end; margin-top: .8rem; }
  .pattern-status a { margin-bottom: 0; gap: .3rem; }
</style>
