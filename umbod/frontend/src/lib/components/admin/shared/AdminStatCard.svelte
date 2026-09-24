<script lang="ts">
  import type { Snippet } from 'svelte';

  type Props = {
    label: string;
    children: Snippet;
  };

  let { label, children }: Props = $props();
</script>

<div class="stat-card">
  <dt>{label}</dt>
  <dd>{@render children()}</dd>
</div>

<style>
  .stat-card {
    background: #ffffff;
    border: 1px solid #e9e9e7;
    border-radius: 8px;
    min-width: 0;
    padding: 0.85rem;
  }

  dt {
    color: #afaeab;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    line-height: 1.4;
    text-transform: uppercase;
  }

  dd {
    color: #37352f;
    font-size: 0.9rem;
    line-height: 1.45;
    margin: 0.3rem 0 0;
    overflow-wrap: anywhere;
  }

  dd :global(p) {
    color: #787774;
    font-size: 0.8rem;
    line-height: 1.4;
    margin: 0.45rem 0 0;
  }
</style>
