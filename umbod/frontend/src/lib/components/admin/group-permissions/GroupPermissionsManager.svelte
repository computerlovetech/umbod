<script lang="ts">
  import { enhance } from '$app/forms';
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
                    action="?/deletePermissionGroup"
                    use:enhance={() => {
                      state.closeGroupMenu();
                      const pendingKey = `delete-group:${group.groupId}`;
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
        action="?/registerPermissionGroup"
        class="group-permissions__add"
        use:enhance={() => {
          const pendingKey = 'register-group';
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
          action="?/saveGroupPermissions"
          class="group-permissions__save"
          use:enhance={() => {
            const pendingKey = savePendingKey(state.selectedGroupId);
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
    background: #eef6ff;
    border: 1px solid #b6d7f2;
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
    border-top: 1px solid #f0efec;
    display: flex;
    position: relative;
  }

  .group-permissions__group-row:hover {
    background: #f4f4f2;
  }

  .group-permissions__group-button {
    align-items: center;
    background: transparent;
    border: 0;
    color: #37352f;
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
    background: #fff;
    box-shadow: inset 3px 0 0 #37352f;
  }

  .group-permissions__avatar {
    align-items: center;
    background: #37352f;
    border-radius: 50%;
    color: #fff;
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
    display: block;
    flex: 1;
    font-size: 13px;
    font-weight: 600;
    min-width: 0;
  }

  .group-permissions__add {
    border-top: 1px solid #e9e9e7;
    margin-top: auto;
    padding: 13px 15px;
  }

  .group-permissions__add label {
    color: #787774;
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
    border: 1px solid #e2e1de;
    border-radius: 7px;
    color: #37352f;
    flex: 1;
    font: inherit;
    min-width: 0;
    padding: 8px 9px;
  }

  .group-permissions__edit-button {
    background: #fff;
    border: 1px solid #e2e1de;
    border-radius: 6px;
    color: #37352f;
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
    background: #37352f;
    border-color: #37352f;
    color: #fff;
  }

  .group-permissions__detail-head {
    align-items: flex-start;
    display: flex;
    gap: 12px;
    margin-bottom: 6px;
  }

  .group-permissions__detail-head h2 {
    font-size: 20px;
    letter-spacing: -0.3px;
    margin: 0;
  }

  .group-permissions__detail-head p,
  .group-permissions__description,
  .group-permissions__block > p {
    color: #787774;
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
    border: 1px solid #e9e9e7;
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
    color: #afaeab;
    font-size: 13px;
    font-weight: 500;
  }

  .group-permissions__stat-card p {
    color: #787774;
    font-size: 11px;
    margin: 1px 0 0;
  }

  .group-permissions__block h3 {
    color: #afaeab;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.5px;
    margin: 0 0 4px;
    text-transform: uppercase;
  }

  .group-permissions__block > p {
    color: #afaeab;
    margin-bottom: 12px;
  }

  .group-permissions__connector {
    border-bottom: 1px solid #f4f4f2;
  }

  .group-permissions__connector:last-child {
    border-bottom: 0;
  }

  .group-permissions__connector-row {
    align-items: center;
    display: flex;
    gap: 11px;
    padding: 11px 0;
  }

  .group-permissions__connector-icon {
    align-items: center;
    background: #fff;
    border: 1px solid #ececea;
    border-radius: 6px;
    color: #37352f;
    display: inline-flex;
    flex-shrink: 0;
    font-size: 11px;
    font-weight: 700;
    height: 24px;
    justify-content: center;
    width: 24px;
  }

  .group-permissions__connector-name {
    flex: 1;
    font-weight: 600;
    min-width: 0;
  }

  .group-permissions__connector-name span {
    color: #afaeab;
    display: block;
    font-size: 11px;
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
    background: #f4f4f2;
    border: 1px solid #e9e9e7;
    color: #787774;
  }

  .group-permissions__tag-green {
    background: #edf9f4;
    border: 1px solid #c5e8d5;
    color: #1a7f4b;
  }

  .group-permissions__tag-orange {
    background: #fff6ee;
    border: 1px solid #fdd8a8;
    color: #b35b00;
  }

  .group-permissions__operations-wrap {
    min-width: 0;
    padding: 2px 0 16px 39px;
  }

  .group-permissions__operations {
    background: #fafaf9;
    border: 1px solid #e9e9e7;
    border-radius: 9px;
    min-width: 0;
    padding: 4px 14px;
  }

  .group-permissions__operations-heading {
    border-bottom: 1px solid #ececea;
    color: #787774;
    font-size: 12px;
    padding: 11px 0 9px;
  }

  .group-permissions__section-heading {
    color: #afaeab;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.4px;
    padding: 12px 0 4px;
    text-transform: uppercase;
  }

  .group-permissions__operation {
    align-items: flex-start;
    border-bottom: 1px solid #f4f4f2;
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
    background: #eef6ff;
    border-radius: 6px;
    outline: 2px solid #3b82c4;
    outline-offset: 2px;
  }

  .group-permissions__operation > span {
    flex: 1;
    min-width: 0;
  }

  .group-permissions__operation code {
    color: #37352f;
    display: block;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12.5px;
    overflow-wrap: anywhere;
    word-break: break-word;
  }

  .group-permissions__operation span span {
    color: #afaeab;
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
    color: #b42318;
  }

  .group-permissions__success {
    color: #067647;
  }

  .group-permissions__warning,
  .group-permissions__warning-panel {
    color: #92400e;
  }

  @media (max-width: 820px) {
    .group-permissions__connector-row {
      align-items: flex-start;
      flex-wrap: wrap;
    }

    .group-permissions__operations-wrap {
      padding-left: 0;
    }

    .group-permissions__tag {
      order: 3;
    }

    .group-permissions__edit-button {
      margin-left: auto;
    }
  }
</style>
