<script lang="ts">
  import { permissions, permissionLabels } from '$lib/admin/filesystem/domain/schemas';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import { filesystemConfirmation } from './confirmation-dialog';
  import type { FilesystemGroupEditorState } from './filesystem-group-editor-state.svelte';
  let { editor }: { editor: FilesystemGroupEditorState } = $props();
</script>

<dialog aria-labelledby="filesystem-group-title" aria-describedby="filesystem-group-description" {@attach filesystemConfirmation(editor.cancel)}>
  <h2 id="filesystem-group-title">{editor.editingId === null ? 'Add group' : 'Edit group'}</h2>
  <p id="filesystem-group-description">Configure direct root access. Changes apply only after saving the policy.</p>
  {#if editor.draft}
    <form onsubmit={(event) => { event.preventDefault(); editor.apply(); }}>
      <label for="filesystem-group-id">Group ID</label>
      <input id="filesystem-group-id" value={editor.draft.group_id} oninput={(event) => editor.edit('group_id', event.currentTarget.value)} autocomplete="off" spellcheck="false" placeholder="Exact group ID" />
      <label for="filesystem-group-issuer">Identity issuer</label>
      <input id="filesystem-group-issuer" value={editor.draft.issuer} oninput={(event) => editor.edit('issuer', event.currentTarget.value)} autocomplete="off" spellcheck="false" placeholder="Issuer URL" />
      <fieldset>
        <legend>Permissions</legend>
        {#each permissions as permission (permission)}
          <label class="permission">
            <input type="checkbox" checked={editor.draft.permissions.includes(permission)} onchange={(event) => editor.toggle(permission, event.currentTarget.checked)} />
            {permissionLabels[permission]}
          </label>
        {/each}
      </fieldset>
      {#if editor.draft.permissions.includes('write') && !editor.draft.permissions.includes('discover')}
        <p class="hint">Also select Browse root to allow creation.</p>
      {/if}
      {#if editor.validationMessage}<p class="hint" role="status">{editor.validationMessage}</p>{/if}
      <div class="actions">
        <button type="button" data-dialog-cancel onclick={(event) => { event.currentTarget.closest('dialog')?.close(); editor.cancel(); }}>Cancel</button>
        <Button type="submit" disabled={!!editor.validationMessage}>{editor.editingId === null ? 'Add group' : 'Apply changes'}</Button>
      </div>
    </form>
  {/if}
</dialog>

<style>
  dialog { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel); box-shadow: var(--admin-shadow-dialog); box-sizing: border-box; color: var(--admin-ink); max-height: calc(100dvh - 2rem); max-width: 36rem; overflow: auto; padding: 1.5rem; width: calc(100% - 2rem); }
  dialog::backdrop { background: var(--admin-overlay); }
  h2 { font-size: 1.25rem; margin: 0; }
  p { color: var(--admin-muted); font-size: 13px; line-height: 1.6; }
  form > label { display: block; font-size: 13px; font-weight: 600; margin: 1rem 0 0.4rem; }
  input:not([type="checkbox"]) { background: var(--admin-panel); border: 1px solid var(--admin-border-strong); border-radius: var(--admin-radius); box-sizing: border-box; color: var(--admin-ink); font: inherit; padding: 0.65rem 0.75rem; width: 100%; }
  fieldset { border: 0; display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 1.25rem 0 0; padding: 0; }
  legend { font-size: 13px; font-weight: 600; margin-bottom: 0.6rem; }
  .permission { align-items: center; background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); cursor: pointer; display: flex; font-size: 13px; gap: 0.5rem; padding: 0.6rem; }
  input[type="checkbox"] { accent-color: var(--admin-accent); }
  .actions { display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 1.5rem; }
  button { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); color: var(--admin-ink); cursor: pointer; font: inherit; padding: 0.6rem 0.9rem; }
  input:focus-visible, button:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: 2px; }
</style>
