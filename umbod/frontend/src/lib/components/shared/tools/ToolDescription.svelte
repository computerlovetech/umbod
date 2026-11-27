<script lang="ts">
  import Disclosure from '#lib/components/shared/Disclosure.svelte';

  let { description }: { description: string } = $props();
</script>

{#if description}
  {#if description.length > 180 || description.includes('\n')}
    <div class="tool-description">
      <Disclosure>
        {#snippet label(expanded: boolean)}
          <span class="description-label">
            {#if !expanded}
              <span class="preview" aria-hidden="true">{description}</span>
            {/if}
            <span class="toggle-label">{expanded ? 'Hide full description' : 'Show full description'}</span>
          </span>
        {/snippet}
        <p class="full-description">{description}</p>
      </Disclosure>
    </div>
  {:else}
    <p class="short-description">{description}</p>
  {/if}
{/if}

<style>
  .tool-description, .short-description { color: var(--admin-muted); font-size: 0.875rem; line-height: 1.55; margin: 0.7rem 0 0; overflow-wrap: anywhere; }
  .description-label { min-width: 0; }
  .preview { display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; white-space: pre-line; }
  .toggle-label { display: block; color: var(--admin-accent); font-size: 0.75rem; font-weight: 600; text-decoration: underline; text-underline-offset: 3px; }
  .preview + .toggle-label { margin-top: 0.35rem; }
  .full-description { font: inherit; margin: 0.5rem 0 0; white-space: pre-line; }
</style>
