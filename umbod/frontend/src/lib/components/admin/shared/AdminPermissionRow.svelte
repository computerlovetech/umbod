<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    name: string;
    description: string;
    icon: Snippet;
    actions?: Snippet;
    details?: Snippet;
  }

  let { name, description, icon, actions, details }: Props = $props();
</script>

<li>
  <div class="row">
    <div class="identity">
      {@render icon()}
      <div class="copy">
        <span class="name">{name}</span>
        {#if description}<p>{description}</p>{/if}
      </div>
    </div>
    {#if actions}<div class="actions">{@render actions()}</div>{/if}
  </div>
  {@render details?.()}
</li>

<style>
  li { border-top: 1px solid var(--admin-border); container-type: inline-size; }
  .row { align-items: center; display: flex; flex-wrap: wrap; gap: 1rem; padding: 1rem 0; }
  .identity { align-items: center; display: flex; flex: 1 1 10rem; gap: 0.75rem; min-width: 0; }
  .copy { min-width: 0; overflow-wrap: anywhere; }
  .name { font-size: 0.9375rem; font-weight: 600; }
  p { color: var(--admin-muted); font-size: 0.875rem; margin: 0.35rem 0 0; white-space: pre-wrap; }
  .actions { min-width: 0; }
  @container (max-width: 35rem) {
    .row { align-items: start; flex-direction: column; }
    .identity { flex-basis: auto; max-width: 100%; }
    .actions { max-width: 100%; }
  }
</style>
