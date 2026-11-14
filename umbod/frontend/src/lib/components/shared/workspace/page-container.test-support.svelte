<script lang="ts">
  import PageContainer from './PageContainer.svelte';

  let { title, detail, showActions }: {
    title: string;
    detail: string;
    showActions: boolean;
  } = $props();
</script>

{#snippet identity()}<h1>{title}</h1>{/snippet}
{#snippet actions()}<button type="button">Create item</button>{/snippet}

<PageContainer {identity} actions={showActions ? actions : undefined}>
  <aside aria-label="Item navigation"><button type="button">Selected item</button></aside>
  <section aria-label="Item details"><p>{detail}</p><input aria-label="Draft" /></section>
</PageContainer>
