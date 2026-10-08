<script lang="ts">
  import { browserSubmit } from '$lib/admin/operations/browser-submit';
  import { untrack } from 'svelte';
  import AdminSplitWorkspace from '$lib/components/admin/shared/AdminSplitWorkspace.svelte';
  import AdminSidebarActionMenu from '$lib/components/admin/shared/AdminSidebarActionMenu.svelte';
  import AdminToggle from '$lib/components/admin/shared/AdminToggle.svelte';
  import AdminSaveAction from '$lib/components/admin/shared/AdminSaveAction.svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import DelayedSpinner from '$lib/components/admin/shared/DelayedSpinner.svelte';
  import LoadingButton from '$lib/components/admin/shared/LoadingButton.svelte';
  import { FormPendingState } from '$lib/components/admin/shared/form-pending-state.svelte';
  import { useToast } from '$lib/components/feedback';
  import { GroupPermissionsState, type ConnectorPermissionTarget, type GroupPermissionsInitialData } from './group-permissions-state.svelte';

  type GroupPermissionsForm = {
    status?: 'saved' | 'registered' | 'deleted' | 'rejected' | 'failed';
    groupId?: string;
    message?: string;
  };

  let { data, form }: { data: GroupPermissionsInitialData; form?: GroupPermissionsForm } = $props();

  const state = new GroupPermissionsState(
    untrack(() => data),
    null,
    untrack(() => (form?.status === 'registered' || form?.status === 'saved' ? (form.groupId ?? null) : null))
  );
  const pendingState = new FormPendingState();
  const toast = useToast();

  $effect(() => {
    const nextData = data;
    const nextSelectedGroupId = form?.status === 'registered' || form?.status === 'saved' ? (form.groupId ?? null) : null;

    untrack(() => state.synchronizeServerData(nextData, null, nextSelectedGroupId));
  });

  const inputValue = (event: Event): string => {
    return event.currentTarget instanceof HTMLInputElement ? event.currentTarget.value : '';
  };

  const inputChecked = (event: Event): boolean => {
    return event.currentTarget instanceof HTMLInputElement ? event.currentTarget.checked : false;
  };

  const isRecord = (value: unknown): value is Record<string, unknown> => {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  };

  const formFromActionResult = (result: unknown): GroupPermissionsForm | null => {
    if (!isRecord(result) || !isRecord(result.data)) return null;
    const { status, groupId, message } = result.data;
    if (status !== 'saved' && status !== 'registered' && status !== 'deleted' && status !== 'rejected' && status !== 'failed') return null;
    if (groupId !== undefined && typeof groupId !== 'string') return null;
    if (message !== undefined && typeof message !== 'string') return null;
    return { status, groupId, message };
  };

  const connectorBadgeLabel = (connector: ConnectorPermissionTarget): string => {
    if (!state.connectorIsGranted(connector.id)) {
      return 'No access';
    }

    const granted = state.grantedCapabilityCount(connector.id);

    if (granted === 0) {
      return 'No capabilities';
    }

    if (granted === connector.capabilities.length) {
      return `All ${granted} capabilities`;
    }

    return `${granted} / ${connector.capabilities.length} capabilities`;
  };

  const connectorBadgeClass = (connector: ConnectorPermissionTarget): string => {
    if (!state.connectorIsGranted(connector.id) || state.grantedCapabilityCount(connector.id) === 0) {
      return 'group-permissions__tag-muted';
    }

    return state.grantedCapabilityCount(connector.id) === connector.capabilities.length
      ? 'group-permissions__tag-green'
      : 'group-permissions__tag-orange';
  };

  const savePendingKey = (groupId: string | null): string => {
    return `save-permissions:${groupId ?? ''}`;
  };

  const saveFeedback = (groupId: string | null): { message: string; tone: 'success' | 'warning' | 'error' | 'muted' | 'saving'; icon: string } => {
    if (pendingState.isPending(savePendingKey(groupId))) {
      return { message: 'Saving changes…', tone: 'saving', icon: '' };
    }

    if (state.hasUnsavedChanges) {
      return { message: 'Unsaved changes', tone: 'warning', icon: '•' };
    }

    return { message: 'All changes saved', tone: 'muted', icon: '✓' };
  };
</script>

<section class="group-permissions" aria-labelledby="group-permissions-title">
  <div class="group-permissions__header">
    {#if state.originHref !== null}
      <a class="group-permissions__back" href={state.originHref}>← Back to OpenAPI connector</a>
    {/if}
    <p class="admin-eyebrow">Umbod</p>
    <h1 id="group-permissions-title" class="admin-title">Group permissions</h1>
    <p class="admin-lede">Add groups and see what each group's agents can do — which connectors they can access and the operations allowed for each.</p>
  </div>


  {#if state.initialTarget !== null}
    {#if state.deepLinkedTargetAvailable}
      <p class="group-permissions__target-notice" role="status">OpenAPI operation ID <code>{state.initialTarget.operationId}</code> is selected. Choose a group and grant it explicitly, then save.</p>
    {:else}
      <div class="group-permissions__warning-panel" role="alert">This OpenAPI operation is unavailable for assignment. It may be stale, inactive, or outside your access. No permission target was added.</div>
    {/if}
  {/if}

  <AdminSplitWorkspace
    ariaLabel="Group permissions workspace"
    sidebarLabel="Groups"
    sidebarHeading="Groups"
    count={state.groups.length}
    detailLabel="Permission editor"
  >
    {#snippet sidebar()}
      <ul class="group-permissions__groups">
        {#each state.groups as group (group.groupId)}
          <li class="group-permissions__group-item">
            <div class:group-permissions__group-selected={state.selectedGroupId === group.groupId} class="group-permissions__group-row">
              <button class="group-permissions__group-button" type="button" onclick={() => state.selectGroup(group.groupId)}>
                <span class="group-permissions__avatar">{state.connectorInitials(group.groupId)}</span>
                <span class="group-permissions__group-name">{group.groupId}</span>
              </button>
              <AdminSidebarActionMenu open={state.openGroupMenuId === group.groupId} label={`Open actions for ${group.groupId}`} onopenchange={(open) => state.setGroupMenuOpen(group.groupId, open)}>
                {#snippet menu()}
                  <form
                    method="POST"
                    data-operation="deletePermissionGroup"
                    use:browserSubmit={({ onComplete }) => {
                      state.closeGroupMenu();
                      const pendingKey = `delete-group:${group.groupId}`;
                      onComplete(() => pendingState.stop(pendingKey));
      pendingState.start(pendingKey);
                      return async ({ update, result }) => {
                        const actionForm = formFromActionResult(result);
                        if (!actionForm) throw new Error('Invalid delete permission group result');
                        if (actionForm.status === 'deleted') toast.success(`Deleted group ${actionForm.groupId ?? group.groupId}`);
                        else toast.error(actionForm.message ?? 'Could not delete group');
                        await update();
                        pendingState.stop(pendingKey);
                      };
                    }}
                  >
                    <input type="hidden" name="groupId" value={group.groupId} />
                    <LoadingButton type="submit" label="Delete group" loadingLabel="Deleting..." loading={pendingState.isPending(`delete-group:${group.groupId}`)} variant="secondary" />
                  </form>
                {/snippet}
              </AdminSidebarActionMenu>
            </div>
          </li>
        {/each}
      </ul>

      <form
        method="POST"
        data-operation="registerPermissionGroup"
        class="group-permissions__add"
        use:browserSubmit={({ onComplete }) => {
          const pendingKey = 'register-group';
          onComplete(() => pendingState.stop(pendingKey));
      pendingState.start(pendingKey);

          return async ({ update, result }) => {
            const actionForm = formFromActionResult(result);
            if (!actionForm) throw new Error('Invalid register permission group result');
            if (actionForm.status === 'registered') toast.success(`Registered group ${actionForm.groupId ?? ''}`);
            else toast.error(actionForm.message ?? 'Could not register group');
            await update();
            pendingState.stop(pendingKey);
          };
        }}
      >
        <label for="group-permissions-new-group">Add group value</label>
        <div class="group-permissions__add-row">
          <input id="group-permissions-new-group" name="groupId" value={state.groupInput} oninput={(event) => state.updateGroupInput(inputValue(event))} />
          <LoadingButton
            type="submit"
            label="Add"
            loadingLabel="Adding..."
            loading={pendingState.isPending('register-group')}
            variant="secondary"
          />
        </div>
        {#if state.validationMessage !== null}
          <p class="group-permissions__error">{state.validationMessage}</p>
        {/if}
      </form>
    {/snippet}

    {#snippet detail()}
      {#if state.editorStatus === 'loading'}
        <DelayedSpinner active label="Loading group permissions" />
      {:else if state.editorStatus === 'failed'}
        <div class="group-permissions__warning-panel" role="alert">
          <p>{state.editorError ?? 'Permission data could not be loaded'}</p>
          <Button onclick={state.retrySelection}>Retry</Button>
        </div>
      {:else if state.editorStatus === 'ready' && state.selectedGroupId !== null && state.selectedPermissionSet !== null}
        <div class="group-permissions__detail-head">
          <span class="group-permissions__avatar group-permissions__avatar-large">{state.connectorInitials(state.selectedGroupId)}</span>
          <div>
            <h2>{state.selectedGroupId}</h2>
            <p>Group permission set</p>
          </div>
        </div>

        <p class="group-permissions__description">What agents in this group can do. Toggle a connector to grant or revoke access, then expand it to choose which capabilities the agents may use.</p>

        <div class="group-permissions__stats">
          <div class="group-permissions__stat-card">
            <div>{state.selectedPermissionSet.connectorIds.length}<span> / {state.connectors.length}</span></div>
            <p>Connectors</p>
          </div>
        </div>

        {#if state.hasUnsavedChanges}
          <p class="group-permissions__warning">Unsaved changes</p>
        {/if}

        {#if state.unsavedChangesWarning !== null}
          <div class="group-permissions__warning-panel" role="alert">
            <p>{state.unsavedChangesWarning}</p>
            <Button variant="danger" onclick={() => state.resolveUnsavedChanges('discard')}>Discard changes</Button>
            <Button variant="secondary" onclick={() => state.resolveUnsavedChanges('cancel')}>Cancel</Button>
          </div>
        {/if}

        <div class="group-permissions__block">
          <h3>Connectors &amp; permissions</h3>
          <p>{state.exactMatchGuidance} Granting a connector does not grant its capabilities. Expand any connector to grant tools, prompts, and resources individually.</p>

          <div class="group-permissions__connectors">
            {#each state.connectors as connector (connector.id)}
              <article class="group-permissions__connector">
                <div class="group-permissions__connector-row">
                  <span class="group-permissions__connector-icon">{state.connectorInitials(connector.displayName)}</span>
                  <span class="group-permissions__connector-name">
                    {connector.displayName}
                    <span>{connector.description}</span>
                  </span>
                  <span class={`group-permissions__tag ${connectorBadgeClass(connector)}`}>{connectorBadgeLabel(connector)}</span>
                  <button class:group-permissions__button-dark={state.expandedConnectorId === connector.id} class="group-permissions__edit-button" type="button" aria-expanded={state.expandedConnectorId === connector.id} onclick={() => state.toggleConnectorExpansion(connector.id)}>{state.expandedConnectorId === connector.id ? 'Done' : 'Capabilities'}</button>
                  <AdminToggle checked={state.connectorIsGranted(connector.id)} ariaLabel={`${connector.displayName} access`} onchange={(event) => state.setConnectorPermission(connector.id, inputChecked(event))} />
                </div>

                {#if state.expandedConnectorId === connector.id}
                  <div class="group-permissions__operations-wrap">
                    <div class="group-permissions__operations">
                      <div class="group-permissions__operations-heading">Capabilities this group's agents may use through {connector.displayName}</div>
                      {#each state.capabilitiesBySection(connector) as section (section.kind)}
                        <div class="group-permissions__section-heading">{section.label}</div>
                        {#each section.capabilities as capability (`${capability.kind}:${capability.key}`)}
                          <div class:group-permissions__operation-selected={capability.kind === 'tool' && state.selectedOperationId === capability.key} class="group-permissions__operation" aria-current={capability.kind === 'tool' && state.selectedOperationId === capability.key ? 'true' : undefined}>
                            <span>
                              <code>{capability.key}</code>
                              <span>{capability.description}</span>
                            </span>
                            <AdminToggle
                              checked={state.capabilityIsGranted({ connectorId: connector.id, kind: capability.kind, key: capability.key })}
                              disabled={!state.connectorIsGranted(connector.id)}
                              ariaLabel={`${capability.label} permission`}
                              onchange={(event) => state.setCapabilityPermission({ connectorId: connector.id, kind: capability.kind, key: capability.key }, inputChecked(event))}
                            />
                          </div>
                        {/each}
                      {/each}
                    </div>
                  </div>
                {/if}
              </article>
            {/each}
          </div>
        </div>

        {@const currentSaveFeedback = saveFeedback(state.selectedGroupId)}
        <form
          method="POST"
          data-operation="saveGroupPermissions"
          class="group-permissions__save"
          use:browserSubmit={({ onComplete }) => {
            const pendingKey = savePendingKey(state.selectedGroupId);
            onComplete(() => pendingState.stop(pendingKey));
      pendingState.start(pendingKey);

            return async ({ update, result }) => {
              const actionForm = formFromActionResult(result);

              if (!actionForm) throw new Error('Invalid save permissions result');
              if (actionForm.status === 'saved' && typeof actionForm.groupId === 'string') {
                await update();
                state.markGroupSaved(actionForm.groupId);
                toast.success('Permissions saved');
              } else if ((actionForm.status === 'rejected' || actionForm.status === 'failed') && state.selectedGroupId !== null) {
                const message = actionForm.message ?? 'Could not save permissions';
                state.markGroupSaveRejected(state.selectedGroupId, message);
                toast.error(message);
              }

              pendingState.stop(pendingKey);
            };
          }}
        >
          <input type="hidden" name="groupId" value={state.selectedGroupId} />
          <input type="hidden" name="permissionSet" value={state.selectedPermissionChangesJson} />
          <AdminSaveAction
            label="Save permissions"
            loadingLabel="Saving permissions..."
            loading={pendingState.isPending(savePendingKey(state.selectedGroupId))}
            disabled={!state.hasUnsavedChanges}
            message={currentSaveFeedback.message}
            tone={currentSaveFeedback.tone}
            icon={currentSaveFeedback.icon}
          />
        </form>
      {:else}
        <p>Select or add a group to edit permissions.</p>
      {/if}
    {/snippet}
  </AdminSplitWorkspace>
</section>

<style>
  .group-permissions__header {
    margin-bottom: 32px;
  }

  .group-permissions__back {
    color: var(--admin-accent);
    display: inline-block;
    margin-bottom: 16px;
  }

  .group-permissions__target-notice {
    background: var(--admin-accent-soft);
    border: 1px solid var(--admin-accent-border);
    border-radius: 8px;
    padding: 12px 16px;
  }

  .group-permissions__groups {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .group-permissions__group-item {
    position: relative;
  }

  .group-permissions__group-row {
    align-items: center;
    border-top: 1px solid var(--admin-border);
    display: flex;
    position: relative;
  }

  .group-permissions__group-row:hover {
    background: var(--admin-soft);
  }

  .group-permissions__group-button {
    align-items: center;
    background: transparent;
    border: 0;
    color: var(--admin-ink);
    cursor: pointer;
    display: flex;
    flex: 1;
    font: inherit;
    gap: 11px;
    min-width: 0;
    padding: 11px 8px 11px 15px;
    text-align: left;
  }

  .group-permissions__group-selected {
    background: var(--admin-accent-soft);
    box-shadow: inset 3px 0 0 var(--admin-accent);
  }

  .group-permissions__avatar {
    align-items: center;
    background: var(--admin-ink);
    border-radius: 50%;
    color: var(--admin-on-action);
    display: inline-flex;
    flex-shrink: 0;
    font-size: 11px;
    font-weight: 700;
    height: 26px;
    justify-content: center;
    width: 26px;
  }

  .group-permissions__avatar-large {
    font-size: 15px;
    height: 38px;
    width: 38px;
  }

  .group-permissions__group-name {
    overflow-wrap: anywhere;
    display: block;
    flex: 1;
    font-size: 13px;
    font-weight: 600;
    min-width: 0;
  }

  .group-permissions__add {
    border-top: 1px solid var(--admin-border);
    margin-top: auto;
    padding: 13px 15px;
  }

  .group-permissions__add label {
    color: var(--admin-muted);
    display: block;
    font-size: 12px;
    font-weight: 600;
    margin-bottom: 8px;
  }

  .group-permissions__add-row {
    display: flex;
    gap: 8px;
  }

  .group-permissions__add-row input {
    background: var(--admin-panel);
    border: 1px solid var(--admin-border-strong);
    border-radius: 7px;
    color: var(--admin-ink);
    flex: 1;
    font: inherit;
    font-size: 14px;
    min-width: 0;
    padding: 8px 9px;
  }

  .group-permissions__edit-button {
    background: var(--admin-panel);
    border: 1px solid var(--admin-border-strong);
    border-radius: 6px;
    color: var(--admin-ink);
    cursor: pointer;
    flex-shrink: 0;
    font: inherit;
    font-size: 12px;
    font-weight: 700;
    line-height: 1;
    min-width: 52px;
    padding: 6px 10px;
  }

  .group-permissions__button-dark {
    background: var(--admin-ink);
    border-color: var(--admin-ink);
    color: var(--admin-on-action);
  }

  .group-permissions__detail-head {
    align-items: flex-start;
    display: flex;
    gap: 12px;
    margin-bottom: 6px;
  }

  .group-permissions__detail-head > div {
    min-width: 0;
  }

  .group-permissions__detail-head h2 {
    font-size: 22px;
    font-weight: 600;
    letter-spacing: -0.03em;
    overflow-wrap: anywhere;
    margin: 0;
  }

  .group-permissions__detail-head p,
  .group-permissions__description,
  .group-permissions__block > p {
    color: var(--admin-muted);
    font-size: 13px;
    line-height: 1.55;
    margin: 0;
  }

  .group-permissions__description {
    margin-bottom: 18px;
    max-width: 640px;
  }

  .group-permissions__stats {
    display: flex;
    gap: 10px;
    margin-bottom: 26px;
  }

  .group-permissions__stat-card {
    border: 1px solid var(--admin-border);
    border-radius: 8px;
    min-width: 118px;
    padding: 10px 15px;
  }

  .group-permissions__stat-card div {
    font-size: 20px;
    font-weight: 700;
    letter-spacing: -0.3px;
  }

  .group-permissions__stat-card span {
    color: var(--admin-muted);
    font-size: 13px;
    font-weight: 500;
  }

  .group-permissions__stat-card p {
    color: var(--admin-muted);
    font-size: 11px;
    margin: 1px 0 0;
  }

  .group-permissions__block h3 {
    color: var(--admin-muted);
    font-size: 12px;
    font-family: var(--admin-mono);
    font-weight: 500;
    letter-spacing: 0.5px;
    margin: 0 0 4px;
    text-transform: uppercase;
  }

  .group-permissions__block > p {
    color: var(--admin-muted);
    margin-bottom: 12px;
  }

  .group-permissions__connector {
    border-bottom: 1px solid var(--admin-soft);
  }

  .group-permissions__connector:last-child {
    border-bottom: 0;
  }

  .group-permissions__connector-row {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 11px;
    padding: 11px 0;
  }

  .group-permissions__connector-icon {
    align-items: center;
    background: var(--admin-panel);
    border: 1px solid var(--admin-border);
    border-radius: 6px;
    color: var(--admin-ink);
    display: inline-flex;
    flex-shrink: 0;
    font-size: 11px;
    font-weight: 700;
    height: 24px;
    justify-content: center;
    width: 24px;
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

  .group-permissions__save {
    display: flex;
    justify-content: flex-end;
    margin-top: 24px;
  }

  .group-permissions__error,
  .group-permissions__success,
  .group-permissions__warning,
  .group-permissions__warning-panel {
    margin: 12px 0;
  }

  .group-permissions__error {
    color: var(--admin-danger);
  }

  .group-permissions__success {
    color: var(--admin-success-text);
  }

  .group-permissions__warning,
  .group-permissions__warning-panel {
    color: var(--admin-warning-text);
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

  .group-permissions__edit-button:hover {
    background: var(--admin-hover);
    border-color: var(--admin-accent-border);
  }

  .group-permissions__button-dark:hover {
    background: var(--admin-action-hover);
    border-color: var(--admin-action-hover);
  }

  .group-permissions__warning-panel {
    background: var(--admin-warning-bg);
    border: 1px solid var(--admin-warning-border);
    border-radius: var(--admin-radius);
    font-size: 14px;
    line-height: 1.6;
    padding: 14px 16px;
  }

  .group-permissions__warning-panel p {
    margin: 0 0 12px;
  }

  @media (max-width: 820px) {
    .group-permissions__connector-row {
      align-items: center;
      display: grid;
      gap: 10px 8px;
      grid-template-columns: 24px minmax(0, 1fr) auto 34px;
    }

    .group-permissions__connector-name {
      grid-column: 2 / -1;
    }

    .group-permissions__operations-wrap {
      padding-left: 0;
    }

    .group-permissions__tag {
      grid-column: 2;
      justify-self: start;
      white-space: normal;
    }

    .group-permissions__edit-button {
      grid-column: 3;
    }
  }
</style>
