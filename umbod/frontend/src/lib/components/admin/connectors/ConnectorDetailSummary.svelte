<script lang="ts">
  import type { Snippet } from 'svelte';
  import AdminPublicationStatus from '#lib/components/admin/shared/AdminPublicationStatus.svelte';
  import ConnectorIcon from './ConnectorIcon.svelte';

  type Props = {
    headingId: string;
    title: string;
    iconDataUrl?: string;
    publicationStatus?: string;
    description?: Snippet;
    technicalDetails?: Snippet;
    children: Snippet;
  } & ({ summary: Snippet; statusOverview?: never } | { statusOverview: Snippet; summary?: never });

  let { headingId, title, iconDataUrl, publicationStatus, description, summary, statusOverview, technicalDetails, children }: Props = $props();
</script>

<article class="connector-detail" aria-labelledby={headingId}>
  <header>
    <div class="heading">
      <ConnectorIcon label={title} dataUrl={iconDataUrl} size="medium" />
      <div class="identity">
        <p class="eyebrow">Connector detail</p>
        <h2 id={headingId}>{title}</h2>
      </div>
    </div>
    {#if publicationStatus !== undefined}
      <AdminPublicationStatus status={publicationStatus} />
    {/if}
  </header>

  {#if description}
    <div class="description">{@render description()}</div>
  {/if}

  {#if statusOverview}
    {@render statusOverview()}
  {:else if summary}
    <dl class="summary-row">{@render summary()}</dl>
  {/if}

  {#if technicalDetails}
    <details class="technical-details">
      <summary>Technical details</summary>
      <div class="reference-list">{@render technicalDetails()}</div>
    </details>
  {/if}

  <div class="body">{@render children()}</div>
</article>

<style>
  .connector-detail { min-width: 0; }
  header { align-items: center; display: flex; gap: 1.25rem; justify-content: space-between; min-height: 2.5rem; }
  .heading { align-items: center; display: flex; gap: 0.8rem; min-width: 0; }
  .identity { min-width: 0; }
  .eyebrow { color: var(--admin-muted); font-size: 0.72rem; font-family: var(--admin-mono); font-weight: 500; letter-spacing: 0.08em; margin: 0 0 0.35rem; text-transform: uppercase; }
  h2 { color: var(--admin-ink); font-size: 1.55rem; font-weight: 600; letter-spacing: -0.035em; line-height: 1.2; margin: 0; overflow-wrap: anywhere; }
  .description { color: var(--admin-muted); line-height: 1.55; margin-top: 1rem; max-width: 48rem; }
  .description :global(p) { margin: 0; }
  .summary-row { border-bottom: 1px solid var(--admin-border); border-top: 1px solid var(--admin-border); display: grid; grid-auto-columns: minmax(0, 1fr); grid-auto-flow: column; margin: 1.25rem 0 0; padding: 0.9rem 0; }
  .summary-row :global(.detail-item) { padding: 0 1.25rem; }
  .summary-row :global(.detail-item:first-child) { padding-left: 0; }
  .summary-row :global(.detail-item + .detail-item) { border-left: 1px solid var(--admin-border); }
  .technical-details { margin-top: 0.8rem; }
  summary { color: var(--admin-ink); cursor: pointer; font-size: 0.9rem; font-weight: 650; padding: 0.45rem 0; }
  .reference-list { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: 8px; margin-top: 0.5rem; }
  .reference-list :global(.reference-group + .reference-group) { border-top: 1px solid var(--admin-border); }
  .body { margin-top: 1.5rem; }

  @media (max-width: 760px) {
    header { align-items: flex-start; flex-direction: column; }
    .summary-row { grid-auto-flow: row; }
    .summary-row :global(.detail-item) { padding: 0.75rem 0; }
    .summary-row :global(.detail-item:first-child) { padding-top: 0; }
    .summary-row :global(.detail-item:last-child) { padding-bottom: 0; }
    .summary-row :global(.detail-item + .detail-item) { border-left: 0; border-top: 1px solid var(--admin-border); }
    .body { margin-top: 1.25rem; }
  }
</style>
