<script lang="ts">
  import type { Snippet } from 'svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import LoadingButton from '#lib/components/admin/shared/LoadingButton.svelte';
  import Disclosure from '#lib/components/shared/Disclosure.svelte';

  let { id, summary, pending, onrun, onreset, children: fields }: {
    id: string;
    summary: string;
    pending: boolean;
    onrun: () => Promise<boolean>;
    onreset: () => void;
    children: Snippet;
  } = $props();

  async function submit(event: SubmitEvent, collapse: () => void): Promise<void> {
    event.preventDefault();
    if (!pending && await onrun()) collapse();
  }
</script>

<div class="query-panel">
  <Disclosure>
    {#snippet label(expanded)}
      <span class="query-trigger">
        <span class="query-label"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 7h16M4 17h16M9 4v6m6 4v6" /></svg>Query</span>
        <span class="query-summary">{summary}</span>
        <span class="query-toggle">{expanded ? 'Close' : 'Edit query'}</span>
      </span>
    {/snippet}
    {#snippet children(collapse)}
      <form {id} novalidate onsubmit={(event) => submit(event, collapse)} aria-busy={pending}>
        {@render fields()}
        <div class="query-actions">
          <Button variant="secondary" size="compact" disabled={pending} onclick={onreset}>Reset</Button>
          <LoadingButton type="submit" size="compact" label="Run query" loadingLabel="Running query" loading={pending} />
        </div>
      </form>
    {/snippet}
  </Disclosure>
</div>

<style>
  .query-panel {
    --disclosure-trigger-radius: 7px 7px 0 0;
    --disclosure-trigger-min-height: 48px;
    --disclosure-trigger-padding: 13px 16px;
    --disclosure-expanded-background: var(--admin-soft);
    border: 1px solid var(--admin-border);
    border-radius: 8px;
    background: var(--admin-panel);
    margin-bottom: 20px;
    min-width: 0;
  }
  .query-trigger { display: flex; align-items: center; gap: 18px; flex: 1; min-width: 0; font-size: .8125rem; }
  .query-label { display: flex; align-items: center; gap: 8px; font-weight: 600; flex-shrink: 0; }
  svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; color: var(--admin-muted); }
  .query-summary { color: var(--admin-muted); min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .query-toggle { color: var(--admin-muted); margin-left: auto; white-space: nowrap; flex-shrink: 0; }
  form { border-top: 1px solid var(--admin-border); padding: 18px; display: grid; gap: 18px; min-width: 0; }
  .query-actions { display: flex; justify-content: flex-end; gap: 10px; }
  @media (max-width: 700px) { .query-panel { --disclosure-trigger-padding: 12px; } .query-trigger { gap: 10px; } .query-summary, .query-toggle { font-size: .75rem; } form { padding: 14px; } }
</style>
