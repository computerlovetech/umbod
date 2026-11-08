<script lang="ts">
  import ActionMenu from '$lib/components/shared/ActionMenu.svelte';
  import type { NodeSummary } from '$lib/files/domain/schemas';
  import type { DescriptionState } from '$lib/files/state/description-state.svelte';
  import type { NodeUpdateState } from '$lib/files/state/node-update-state.svelte';
  import type { SharingEligibilityState } from '$lib/files/state/sharing-eligibility-state.svelte';
  import type { DeletionState } from '$lib/files/state/deletion-state.svelte';
  import { NodeActionsState } from './node-actions-state.svelte';
  import NodeUpdateDialog from './NodeUpdateDialog.svelte';
  import NodeDescriptionDialog from './NodeDescriptionDialog.svelte';
  import FileDeletionDialog from './FileDeletionDialog.svelte';
  import NodeActionIcon from './NodeActionIcon.svelte';

  let { update, description, name, signIn, node, sharing, deletion, onconfirm }: { update: NodeUpdateState; description: DescriptionState; name: string; signIn: () => void; node?: NodeSummary; sharing?: SharingEligibilityState; deletion?: DeletionState; onconfirm?: () => void } = $props();
  const menuState = new NodeActionsState(() => ({ update, description, node, sharing, deletion }));
</script>

{#if menuState.available}
  <div class="node-actions" {@attach menuState.attach}>
    <ActionMenu open={menuState.open} label={`Actions for “${name || 'Files'}”`} onopenchange={menuState.setOpen} --action-menu-trigger-size="var(--node-actions-trigger-size, 2.75rem)" --action-menu-trigger-z-index="1" --action-menu-min-width="12.5rem">
      {#snippet trigger()}
        <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><circle cx="5" cy="12" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="19" cy="12" r="1.5" /></svg>
      {/snippet}
      {#snippet menu()}
        {#if menuState.canShare}<button role="menuitem" aria-label={`Share “${name}”`} disabled={menuState.busy} onclick={menuState.share}><span class="action-label"><NodeActionIcon action="share" />Share</span></button>{/if}
        {#if update.canRename}<button role="menuitem" disabled={menuState.busy || update.open || description.open} onclick={() => menuState.run(update.showRename)}><span class="action-label"><NodeActionIcon action="rename" />Rename</span></button>{/if}
        {#if description.available}<button role="menuitem" disabled={menuState.busy || update.open || description.open} onclick={() => menuState.run(description.show)}><span class="action-label"><NodeActionIcon action="description" />Edit description</span></button>{/if}
        {#if update.canMove}<button role="menuitem" disabled={menuState.busy || update.open || description.open} onclick={() => menuState.run(update.showMove)}><span class="action-label"><NodeActionIcon action="move" />Move</span></button>{/if}
        {#if update.probeFailed}<button role="menuitem" onclick={() => menuState.run(update.checkEligibility)}><span class="action-label"><NodeActionIcon action="retry" />Retry rename and move check</span></button>{/if}
        {#if update.needsReload && !update.open}<button role="menuitem" disabled={menuState.busy} onclick={() => menuState.run(update.reload)}><span class="action-label"><NodeActionIcon action="retry" />Reload item</span></button>{/if}
        {#if description.eligibility === 'error'}<button role="menuitem" onclick={() => menuState.run(description.checkEligibility)}><span class="action-label"><NodeActionIcon action="retry" />Retry description check</span></button>{/if}
        {#if description.needsReload && !description.open}<button role="menuitem" disabled={menuState.busy} onclick={() => menuState.run(description.reload)}><span class="action-label"><NodeActionIcon action="retry" />Reload description</span></button>{/if}
        {#if description.eligibility === 'sign-in'}<button role="menuitem" onclick={() => menuState.run(signIn)}><span class="action-label"><NodeActionIcon action="sign-in" />Sign in</span></button>{/if}
        {#if deletion && (deletion.available || deletion.pending)}<button role="menuitem" class="danger" aria-label={`Delete “${name}”`} aria-busy={deletion.pending} disabled={menuState.busy || !!deletion.confirmation} onclick={() => menuState.run(deletion!.show)}><span class="action-label"><NodeActionIcon action="delete" />{deletion.pending ? 'Deleting…' : 'Delete'}</span></button>{/if}
      {/snippet}
    </ActionMenu>
  </div>
{/if}
{#if update.open}<div {@attach menuState.restoreAfterDialog}><NodeUpdateDialog state={update} /></div>{/if}
{#if description.open}<div {@attach menuState.restoreAfterDialog}><NodeDescriptionDialog state={description} {name} /></div>{/if}
{#if deletion?.confirmation}<div {@attach menuState.restoreAfterDialog}><FileDeletionDialog state={deletion} {onconfirm} /></div>{/if}
{#if description.error && !description.open}<p role="alert">{description.error}</p>{/if}
<p class="description-status" role="status" aria-atomic="true">{description.status}</p>

<style>
  .node-actions { position: relative; display: inline-flex; vertical-align: middle; text-align: left; }
  .action-label { display: flex; align-items: center; gap: 0.65rem; white-space: normal; }
  .node-actions button.danger { color: var(--admin-danger); }
  .node-actions button.danger:hover:not(:disabled) { background: color-mix(in srgb, var(--admin-danger) 8%, var(--admin-panel)); }
  .description-status { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
  [role='alert'] { color: var(--admin-danger); }
</style>
