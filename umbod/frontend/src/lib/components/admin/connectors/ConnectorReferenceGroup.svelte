<script lang="ts">
  import type { Snippet } from 'svelte';

  let { title, children }: { title: string; children: Snippet } = $props();
</script>

<section class="reference-group">
  <h3>{title}</h3>
  <dl>{@render children()}</dl>
</section>

<style>
  .reference-group { container: connector-reference / inline-size; }
  h3 { background: var(--admin-soft); border-radius: 7px 7px 0 0; color: var(--admin-ink); font-size: 0.85rem; font-weight: 650; margin: 0; padding: 0.4rem 0.75rem; }
  .reference-group:not(:first-child) h3 { border-radius: 0; }
  dl { margin: 0; }
  dl > :global(.detail + .detail) { border-top: 1px solid var(--admin-border); }
</style>
