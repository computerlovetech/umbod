<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import { nativeDialog } from './native-dialog';
  import type { GroupRegistrationState } from './group-registration-state.svelte';
  let { registration }: { registration: GroupRegistrationState } = $props();
</script>

<dialog aria-labelledby="group-registration-title" aria-describedby="group-registration-description" {@attach nativeDialog(registration.cancel, () => !registration.pending)}>
  <h2 id="group-registration-title">Add group</h2>
  <p id="group-registration-description">Register a shared group claim value for connectors and filesystem access. This does not create IdP membership. Registration is saved immediately and independently of permission changes. It grants no access.</p>
  <form onsubmit={(event) => { event.preventDefault(); void registration.submit(); }}>
    <label for="catalogue-group-id">Group ID</label>
    <input id="catalogue-group-id" value={registration.groupId} oninput={(event) => registration.edit(event.currentTarget.value)} disabled={registration.pending} autocomplete="off" spellcheck="false" placeholder="Exact group ID" />
    <p>Match the JWT group value exactly, including case, spaces and punctuation.</p>
    {#if registration.error}<p role="alert">{registration.error}</p>{/if}
    <div class="actions">
      <button type="button" data-dialog-cancel disabled={registration.pending} onclick={registration.cancel}>Cancel</button>
      <Button type="submit" disabled={!registration.valid || registration.pending}>{registration.pending ? 'Registering…' : 'Register group'}</Button>
    </div>
  </form>
</dialog>

<style>
  dialog { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel); color: var(--admin-ink); max-width: 36rem; padding: 1.5rem; width: calc(100% - 2rem); box-sizing: border-box; }
  dialog::backdrop { background: var(--admin-overlay); }
  h2 { font-size: 1.25rem; margin: 0; }
  p { color: var(--admin-muted); font-size: 13px; line-height: 1.6; }
  label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 0.4rem; }
  input { background: var(--admin-panel); border: 1px solid var(--admin-border-strong); border-radius: var(--admin-radius); box-sizing: border-box; color: var(--admin-ink); font: inherit; padding: 0.65rem 0.75rem; width: 100%; }
  .actions { display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 1.5rem; }
  button { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); color: var(--admin-ink); cursor: pointer; padding: 0.6rem 0.9rem; }
</style>
