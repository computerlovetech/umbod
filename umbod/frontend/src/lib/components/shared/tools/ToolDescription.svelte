<script lang="ts">
  let { description }: { description: string } = $props();
</script>

{#if description}
  {#if description.length > 180 || description.includes('\n')}
    <details class="tool-description">
      <summary>
        <span class="preview" aria-hidden="true">{description}</span>
        <span class="expand-label">Show full description</span>
        <span class="collapse-label">Hide full description</span>
      </summary>
      <p class="full-description">{description}</p>
    </details>
  {:else}
    <p class="short-description">{description}</p>
  {/if}
{/if}

<style>
  .tool-description, .short-description { color: var(--admin-muted); font-size: 0.875rem; line-height: 1.55; margin: 0.7rem 0 0; overflow-wrap: anywhere; }
  summary { cursor: pointer; list-style: none; }
  summary::-webkit-details-marker { display: none; }
  summary:focus-visible { border-radius: 4px; outline: 3px solid var(--admin-focus); outline-offset: 3px; }
  .preview { display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; white-space: pre-line; }
  .expand-label, .collapse-label { color: var(--admin-accent); font-size: 0.75rem; font-weight: 600; text-decoration: underline; text-underline-offset: 3px; }
  .expand-label { display: inline-block; margin-top: 0.35rem; }
  .collapse-label { display: none; }
  details[open] .preview, details[open] .expand-label { display: none; }
  details[open] .collapse-label { display: inline; }
  .full-description { font: inherit; margin: 0.5rem 0 0; white-space: pre-line; }
</style>
