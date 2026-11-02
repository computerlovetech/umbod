<script lang="ts">
  import type { DescriptionState } from '$lib/files/state/description-state.svelte';
  let { state, signIn }: { state: DescriptionState; signIn: () => void } = $props();
  const id = $props.id();
</script>

<section aria-label="Description">
  <h2>Description</h2>
  {#if state.description}<p class="description">{state.description}</p>{:else}<p>No description.</p>{/if}
  {#if state.open}
    <form aria-label="Edit description" aria-busy={state.pending} onsubmit={(event) => { event.preventDefault(); void state.save(); }}>
      <label for={id + '-description'}>Description</label>
      <p id={id + '-hint'}>What is here, and when should it be read?</p>
      <textarea id={id + '-description'} aria-describedby={id + '-hint'} value={state.draft} oninput={(event) => state.change(event.currentTarget.value)} disabled={state.pending || state.needsReload} rows="4"></textarea>
      <div class="actions">
        <button type="submit" disabled={!state.canSave}>{state.pending ? 'Saving…' : 'Save description'}</button>
        <button type="button" onclick={state.cancel} disabled={state.pending}>Cancel</button>
      </div>
    </form>
  {:else if state.available}
    <button onclick={state.show}>Edit description</button>
  {/if}
  {#if state.error}<p role="alert">{state.error}</p>{/if}
  {#if state.needsReload}<button onclick={state.reload} disabled={state.pending}>Reload item</button>{/if}
  {#if state.eligibility === 'error'}
    <p>Couldn't check description editing availability.</p>
    <button onclick={state.checkEligibility}>Retry description check</button>
  {:else if state.eligibility === 'sign-in'}
    <button onclick={signIn}>Sign in</button>
  {/if}
  <p role="status" aria-atomic="true">{state.pending ? 'Saving description…' : state.status}</p>
</section>

<style>
  section { margin: 1rem 0; }
  h2 { font-size: 1rem; }
  p { color: var(--admin-muted); }
  .description { white-space: pre-wrap; overflow-wrap: anywhere; }
  textarea { display: block; box-sizing: border-box; width: 100%; margin-bottom: 0.6rem; resize: vertical; }
  textarea, button { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-panel); color: var(--admin-ink); font: inherit; padding: 0.6rem; }
  .actions { display: flex; gap: 0.6rem; }
  button { cursor: pointer; }
  button:disabled { opacity: 0.6; cursor: default; }
  [role='alert'] { color: var(--admin-danger); }
</style>
