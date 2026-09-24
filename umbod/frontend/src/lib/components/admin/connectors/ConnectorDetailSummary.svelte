<script lang="ts">
  import type { Snippet } from 'svelte';
  import AdminPublicationStatus from '$lib/components/admin/shared/AdminPublicationStatus.svelte';
  import ConnectorIcon from './ConnectorIcon.svelte';

  type Props = {
    headingId: string;
    title: string;
    iconDataUrl?: string;
    publicationStatus: string;
    description?: Snippet;
    summary: Snippet;
    technicalDetails?: Snippet;
    children: Snippet;
  };

  let { headingId, title, iconDataUrl, publicationStatus, description, summary, technicalDetails, children }: Props = $props();
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
    <AdminPublicationStatus status={publicationStatus} />
  </header>

  {#if description}
    <div class="description">{@render description()}</div>
  {/if}

  <dl class="summary-row">
    {@render summary()}
  </dl>

  {#if technicalDetails}
    <details class="technical-details">
      <summary>Technical details</summary>
      <dl>{@render technicalDetails()}</dl>
    </details>
  {/if}

  <div class="body">{@render children()}</div>
</article>

<style>
  .connector-detail { min-width: 0; }
  header { align-items: center; display: flex; gap: 1.25rem; justify-content: space-between; min-height: 2.5rem; }
  .heading { align-items: center; display: flex; gap: 0.8rem; min-width: 0; }
  .identity { min-width: 0; }
  .eyebrow { color: #afaeab; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.12em; margin: 0 0 0.35rem; text-transform: uppercase; }
  h2 { color: #37352f; font-size: 1.55rem; line-height: 1.2; margin: 0; overflow-wrap: anywhere; }
  .description { color: #787774; line-height: 1.55; margin-top: 1rem; max-width: 48rem; }
  .description :global(p) { margin: 0; }
  .summary-row { border-bottom: 1px solid #e9e9e7; border-top: 1px solid #e9e9e7; display: grid; grid-auto-columns: minmax(0, 1fr); grid-auto-flow: column; margin: 1.25rem 0 0; padding: 0.9rem 0; }
  .summary-row :global(.detail-item) { padding: 0 1.25rem; }
  .summary-row :global(.detail-item:first-child) { padding-left: 0; }
  .summary-row :global(.detail-item + .detail-item) { border-left: 1px solid #e9e9e7; }
  .technical-details { background: #f7f7f5; border: 1px solid #e9e9e7; border-radius: 8px; margin-top: 0.8rem; padding: 0.85rem 1rem; }
  summary { color: #565550; cursor: pointer; font-size: 0.85rem; font-weight: 650; }
  .technical-details dl { display: grid; gap: 1.25rem 2rem; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 1rem 0 0; }
  .body { margin-top: 1.5rem; }

  @media (max-width: 760px) {
    header { align-items: flex-start; flex-direction: column; }
    .summary-row { grid-auto-flow: row; }
    .summary-row :global(.detail-item) { padding: 0.75rem 0; }
    .summary-row :global(.detail-item:first-child) { padding-top: 0; }
    .summary-row :global(.detail-item:last-child) { padding-bottom: 0; }
    .summary-row :global(.detail-item + .detail-item) { border-left: 0; border-top: 1px solid #e9e9e7; }
    .technical-details dl { grid-template-columns: 1fr; }
    .body { margin-top: 1.25rem; }
  }
</style>
