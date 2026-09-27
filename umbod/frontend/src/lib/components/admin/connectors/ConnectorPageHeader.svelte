<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  type Props = {
    title: string;
    lede: string;
    addLabel: string;
    onadd: (trigger: HTMLButtonElement) => void;
  };

  let { title, lede, addLabel, onadd }: Props = $props();
</script>

<div class="connector-page-header">
  <div>
    <p class="admin-eyebrow">Umbod / Connectors</p>
    <h1 class="admin-title">{title}</h1>
    <p class="admin-lede">{lede}</p>
  </div>
  <Button aria-label={addLabel} onclick={(event) => onadd(event.currentTarget)}><span class="plus" aria-hidden="true">+</span>{addLabel}</Button>
</div>

<style>
  .connector-page-header {
    align-items: flex-start;
    display: flex;
    gap: 24px;
    justify-content: space-between;
  }

  .connector-page-header :global(.admin-shared-button) {
    flex-shrink: 0;
    margin-top: 26px;
  }

  .plus {
    font-size: 18px;
    font-weight: 400;
    margin-right: 8px;
  }

  @media (max-width: 1000px) {
    .connector-page-header {
      flex-wrap: wrap;
      gap: 16px;
    }

    .connector-page-header :global(.admin-shared-button) {
      margin-top: 0;
    }
  }
</style>
