<script lang="ts">
  import type { Snippet } from 'svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import LoadingButton from '#lib/components/admin/shared/LoadingButton.svelte';

  let { id, summary, pending, onrun, onreset, children }: {
    id: string;
    summary: string;
    pending: boolean;
    onrun: () => Promise<boolean>;
    onreset: () => void;
    children: Snippet;
  } = $props();

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const form = event.currentTarget;
    if (!(form instanceof HTMLFormElement) || pending) return;
    const panel = form.closest('details');
    const success = await onrun();
    if (success && panel?.isConnected) {
      const restoreFocus = panel.contains(document.activeElement);
      panel.open = false;
      if (restoreFocus) panel.querySelector('summary')?.focus();
    }
  }
</script>

<details class="query-panel">
  <summary>
    <span class="query-label"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 7h16M4 17h16M9 4v6m6 4v6" /></svg>Query</span>
    <span class="query-summary">{summary}</span>
    <span class="query-toggle"><span class="when-closed">Edit query</span><span class="when-open">Close</span><svg aria-hidden="true" viewBox="0 0 24 24"><path d="m7 10 5 5 5-5" /></svg></span>
  </summary>
  <form {id} novalidate onsubmit={submit} aria-busy={pending}>
    {@render children()}
    <div class="query-actions">
      <Button variant="secondary" size="compact" disabled={pending} onclick={onreset}>Reset</Button>
      <LoadingButton type="submit" size="compact" label="Run query" loadingLabel="Running query" loading={pending} />
    </div>
  </form>
</details>

<style>
  .query-panel { border: 1px solid var(--admin-border); border-radius: 8px; background: var(--admin-panel); margin-bottom: 20px; min-width: 0; }
  summary { display: flex; align-items: center; gap: 18px; list-style: none; cursor: pointer; padding: 13px 16px; font-size: .8125rem; min-height: 48px; box-sizing: border-box; }
  summary::-webkit-details-marker { display: none; }
  .query-label { display: flex; align-items: center; gap: 8px; font-weight: 600; flex-shrink: 0; }
  svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; color: var(--admin-muted); }
  .query-summary { color: var(--admin-muted); min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .query-toggle { display: flex; align-items: center; gap: 7px; color: var(--admin-muted); margin-left: auto; white-space: nowrap; flex-shrink: 0; }
  .query-toggle svg { width: 14px; height: 14px; }
  .when-open { display: none; }
  details[open] .when-open { display: inline; }
  details[open] .when-closed { display: none; }
  details[open] .query-toggle svg { transform: rotate(180deg); }
  details[open] > summary { border-bottom: 1px solid var(--admin-border); background: var(--admin-soft); border-radius: 8px 8px 0 0; }
  form { padding: 18px; display: grid; gap: 18px; min-width: 0; }
  .query-actions { display: flex; justify-content: flex-end; gap: 10px; }
  @media (max-width: 700px) { summary { gap: 10px; padding: 12px; } .query-summary, .query-toggle { font-size: .75rem; } form { padding: 14px; } }
</style>
