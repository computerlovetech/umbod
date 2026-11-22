<script lang="ts">
  import AdminPermissionRow from '#lib/components/admin/shared/AdminPermissionRow.svelte';
  import SegmentedRadio from '#lib/components/shared/SegmentedRadio.svelte';
  import AdminToggle from '#lib/components/admin/shared/AdminToggle.svelte';
  import AdminSaveAction from '#lib/components/admin/shared/AdminSaveAction.svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import DelayedSpinner from '#lib/components/admin/shared/DelayedSpinner.svelte';
  import type { GroupPermissionsState, ConnectorPermissionTarget } from './group-permissions-state.svelte';

  let { state }: { state: GroupPermissionsState } = $props();
  const id = $props.id();
  const accessOptions = [
    { value: 'none', label: 'No access' },
    { value: 'granted', label: 'Granted' }
  ] as const;

  const inputChecked = (event: Event): boolean => event.currentTarget instanceof HTMLInputElement && event.currentTarget.checked;

  const connectorBadgeLabel = (connector: ConnectorPermissionTarget): string => {
    if (!state.connectorIsGranted(connector.id)) {
      return 'Access required';
    }

    const granted = state.grantedCapabilityCount(connector.id);

    if (granted === 0) {
      return 'No capabilities granted';
    }

    if (granted === connector.capabilities.length) {
      return granted === 1 ? '1 capability' : `All ${granted} capabilities`;
    }

    return `${granted} / ${connector.capabilities.length} capabilities`;
  };

  const connectorBadgeClass = (connector: ConnectorPermissionTarget): string => {
    if (!state.connectorIsGranted(connector.id)) {
      return 'group-permissions__tag-muted';
    }

    const granted = state.grantedCapabilityCount(connector.id);
    return granted > 0 && granted === connector.capabilities.length
      ? 'group-permissions__tag-green'
      : 'group-permissions__tag-orange';
  };

  const saveFeedback = (): { message: string; tone: 'success' | 'warning' | 'error' | 'muted' | 'saving'; icon: string } => {
    if (state.saving) return { message: 'Saving changes…', tone: 'saving', icon: '' };
    if (state.saveMessage) return { message: state.saveMessage, tone: 'error', icon: '!' };
    if (state.hasUnsavedChanges) return { message: 'Unsaved changes', tone: 'warning', icon: '•' };
    return { message: 'All changes saved', tone: 'muted', icon: '✓' };
  };
</script>

  {#if state.initialTarget !== null}
    {#if state.deepLinkedTargetAvailable}
      <p class="group-permissions__target-notice" role="status">OpenAPI operation ID <code>{state.initialTarget.operationId}</code> is selected. Choose a group and grant it explicitly, then save.</p>
    {:else}
      <div class="group-permissions__warning-panel" role="alert">This OpenAPI operation is unavailable for assignment. It may be stale, inactive, or outside your access. No permission target was added.</div>
    {/if}
  {/if}

      {#if state.editorStatus === 'loading'}
        <DelayedSpinner active label="Loading group permissions" />
      {:else if state.editorStatus === 'failed'}
        <div class="group-permissions__warning-panel" role="alert">
          <p>{state.editorError ?? 'Permission data could not be loaded'}</p>
          <Button onclick={state.retrySelection}>Retry</Button>
        </div>
      {:else if state.editorStatus === 'ready' && state.selectedGroupId !== null && state.selectedPermissionSet !== null}
        {#if state.unsavedChangesWarning !== null}
          <div class="group-permissions__warning-panel" role="alert">
            <p>{state.unsavedChangesWarning}</p>
            <Button variant="danger" onclick={() => state.resolveUnsavedChanges('discard')}>Discard changes</Button>
            <Button variant="secondary" onclick={() => state.resolveUnsavedChanges('cancel')}>Cancel</Button>
          </div>
        {/if}

        {#if state.unavailableGrantedConnectors.length > 0}
          <section class="permission-block" aria-labelledby="unavailable-connector-grants-heading">
            <h3 id="unavailable-connector-grants-heading">Unavailable connectors</h3>
            <p>Removals apply after Save permissions.</p>
            <ul class="group-permissions__unavailable-grants">
              {#each state.unavailableGrantedConnectors as connector (connector.id)}
                <li>
                  <span class="group-permissions__connector-name">
                    {connector.displayName}
                    <span>{connector.id}</span>
                  </span>
                  <span class="group-permissions__tag group-permissions__tag-muted">{connector.status}</span>
                  <Button variant="secondary" aria-label={`Remove saved grants for ${connector.displayName}`} disabled={state.saving} onclick={() => state.removeUnavailableConnectorGrants(connector.id)}>Remove saved grants</Button>
                </li>
              {/each}
            </ul>
          </section>
        {/if}

        <section class="connector-permissions" aria-labelledby={id + '-title'}>
          <h3 id={id + '-title'}>Connectors</h3>
          <ul aria-labelledby={id + '-title'} role="list">
            {#each state.connectors as connector (connector.id)}
              {@const expanded = state.expandedConnectorId === connector.id}
              {@const granted = state.connectorIsGranted(connector.id)}
              {@const detailsId = `${id}-capabilities-${connector.id}`}
              <AdminPermissionRow name={connector.displayName} description={connector.description}>
                {#snippet icon()}
                  <span class="group-permissions__connector-icon" aria-hidden="true">{state.connectorInitials(connector.displayName)}</span>
                {/snippet}
                {#snippet actions()}
                  <div class="connector-actions">
                    <SegmentedRadio size="compact" label="Access" accessibleName={'Access to ' + connector.displayName} options={accessOptions} value={granted ? 'granted' : 'none'} disabled={state.saving} onchange={(access) => state.setConnectorPermission(connector.id, access === 'granted')} />
                    <div class="capability-action">
                      <span id={`${detailsId}-status`} class={`group-permissions__tag ${connectorBadgeClass(connector)}`}>{connectorBadgeLabel(connector)}</span>
                      <Button variant={expanded ? 'primary' : 'secondary'} size="compact" type="button" aria-label={`Capabilities for ${connector.displayName}`} aria-describedby={`${detailsId}-status`} aria-expanded={expanded} aria-controls={detailsId} onclick={() => state.toggleConnectorExpansion(connector.id)}>Capabilities</Button>
                    </div>
                  </div>
                {/snippet}
                {#snippet details()}
                  <div class="group-permissions__operations-wrap" id={detailsId} hidden={!expanded}>
                    {#if expanded}
                      <div class="group-permissions__operations">
                        <div class="group-permissions__operations-heading">{granted ? `Capabilities this group's agents may use through ${connector.displayName}` : 'Grant connector access to assign capabilities.'}</div>
                        {#each state.capabilitiesBySection(connector) as section (section.kind)}
                          <div class="group-permissions__section-heading">{section.label}</div>
                          {#each section.capabilities as capability (`${capability.kind}:${capability.key}`)}
                            {@const selected = capability.kind === 'tool' && state.selectedOperationId === capability.key}
                            <div class={['group-permissions__operation', selected && 'group-permissions__operation-selected']} aria-current={selected ? 'true' : undefined}>
                              <span>
                                <code>{capability.key}</code>
                                <span>{capability.description}</span>
                              </span>
                              <AdminToggle
                                checked={state.capabilityIsGranted({ connectorId: connector.id, kind: capability.kind, key: capability.key })}
                                disabled={state.saving || !granted}
                                ariaLabel={`${capability.label} permission`}
                                onchange={(event) => state.setCapabilityPermission({ connectorId: connector.id, kind: capability.kind, key: capability.key }, inputChecked(event))}
                              />
                            </div>
                          {/each}
                        {:else}
                          <p class="empty">No capabilities available</p>
                        {/each}
                      </div>
                    {/if}
                  </div>
                {/snippet}
              </AdminPermissionRow>
            {:else}
              <li class="empty connector-empty">No connectors available</li>
            {/each}
          </ul>
        </section>

        {@const currentSaveFeedback = saveFeedback()}
        <form class="permission-save" onsubmit={(event) => { event.preventDefault(); void state.save(); }}>
          <AdminSaveAction
            label="Save permissions"
            loadingLabel="Saving permissions..."
            loading={state.saving}
            disabled={!state.canSave}
            message={currentSaveFeedback.message}
            tone={currentSaveFeedback.tone}
            icon={currentSaveFeedback.icon}
          />
        </form>
      {:else}
        <p>Select a group to edit permissions.</p>
      {/if}



<style>
  .group-permissions__target-notice {
    background: var(--admin-accent-soft);
    border: 1px solid var(--admin-accent-border);
    border-radius: 8px;
    padding: 12px 16px;
  }

  .connector-permissions { display: grid; gap: 1rem; }
  .connector-permissions h3 { font-size: 0.9375rem; margin: 0; }
  .connector-permissions ul { list-style: none; margin: 0; padding: 0; }
  .connector-actions { align-items: end; display: flex; flex-wrap: wrap; gap: 0.75rem; }
  .capability-action {
    display: grid;
    gap: 0.25rem;
    grid-template-columns: minmax(0, 1fr);
    inline-size: 9.5rem;
    justify-items: start;
    max-inline-size: 100%;
  }
  .capability-action .group-permissions__tag {
    box-sizing: border-box;
    display: block;
    max-inline-size: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    font-variant-numeric: tabular-nums;
  }
  .empty { color: var(--admin-muted); font-size: 0.875rem; }
  .connector-empty { border-top: 1px solid var(--admin-border); padding: 1rem 0; }

  .group-permissions__connector-icon {
    background: var(--admin-soft);
    border-radius: var(--admin-radius);
    color: var(--admin-muted);
    display: grid;
    flex: none;
    font-size: 0.75rem;
    font-weight: 700;
    height: 2.25rem;
    place-items: center;
    width: 2.25rem;
  }

  .group-permissions__connector-name {
    overflow-wrap: anywhere;
    flex: 1 1 12rem;
    font-weight: 600;
    min-width: 0;
  }

  .group-permissions__connector-name span {
    color: var(--admin-muted);
    display: block;
    font-size: 12px;
    line-height: 1.5;
    font-weight: 400;
    margin-top: 2px;
  }

  .group-permissions__tag {
    align-items: center;
    border-radius: 4px;
    display: inline-flex;
    font-size: 11px;
    font-weight: 600;
    gap: 3px;
    padding: 2px 7px;
    white-space: nowrap;
  }

  .group-permissions__tag-muted {
    background: var(--admin-soft);
    border: 1px solid var(--admin-border);
    color: var(--admin-muted);
  }

  .group-permissions__tag-green {
    background: var(--admin-success-bg);
    border: 1px solid var(--admin-success-border);
    color: var(--admin-success-text);
  }

  .group-permissions__tag-orange {
    background: var(--admin-warning-bg);
    border: 1px solid var(--admin-warning-border);
    color: var(--admin-warning-text);
  }

  .group-permissions__operations-wrap {
    min-width: 0;
    padding: 2px 0 16px 39px;
  }

  .group-permissions__operations {
    background: var(--admin-soft);
    border: 1px solid var(--admin-border);
    border-radius: 9px;
    min-width: 0;
    padding: 4px 14px;
  }

  .group-permissions__operations-heading {
    line-height: 1.5;
    overflow-wrap: anywhere;
    border-bottom: 1px solid var(--admin-border);
    color: var(--admin-muted);
    font-size: 12px;
    padding: 11px 0 9px;
  }

  .group-permissions__section-heading {
    color: var(--admin-muted);
    font-size: 11px;
    font-family: var(--admin-mono);
    font-weight: 500;
    letter-spacing: 0.4px;
    padding: 12px 0 4px;
    text-transform: uppercase;
  }

  .group-permissions__operation {
    align-items: flex-start;
    border-bottom: 1px solid var(--admin-border);
    display: flex;
    font-size: 13px;
    gap: 11px;
    min-width: 0;
    padding: 11px 0;
  }

  .group-permissions__operation:last-child {
    border-bottom: 0;
  }

  .group-permissions__operation-selected {
    background: var(--admin-accent-soft);
    border-radius: 6px;
    outline: 2px solid var(--admin-accent);
    outline-offset: 2px;
  }

  .group-permissions__operation > span {
    flex: 1;
    min-width: 0;
  }

  .group-permissions__operation code {
    color: var(--admin-ink);
    display: block;
    font-family: var(--admin-mono);
    font-size: 12.5px;
    overflow-wrap: anywhere;
    word-break: break-word;
  }

  .group-permissions__operation span span {
    color: var(--admin-muted);
    display: block;
    font-size: 11px;
    margin-top: 1px;
    overflow-wrap: anywhere;
    word-break: break-word;
  }

  .group-permissions__unavailable-grants {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .group-permissions__unavailable-grants li {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    justify-content: space-between;
    padding: 10px 0;
  }

  .group-permissions__target-notice {
    color: var(--admin-accent);
    font-size: 14px;
    line-height: 1.6;
    overflow-wrap: anywhere;
  }

  .group-permissions__target-notice code {
    font-family: var(--admin-mono);
  }

  .group-permissions__warning-panel {
    background: var(--admin-warning-bg);
    border: 1px solid var(--admin-warning-border);
    border-radius: var(--admin-radius);
    color: var(--admin-warning-text);
    font-size: 14px;
    margin: 12px 0;
    line-height: 1.6;
    padding: 14px 16px;
  }

  .group-permissions__warning-panel p {
    margin: 0 0 12px;
  }

  @media (max-width: 820px) {
    .group-permissions__operations-wrap { padding-left: 0; }
  }
</style>
