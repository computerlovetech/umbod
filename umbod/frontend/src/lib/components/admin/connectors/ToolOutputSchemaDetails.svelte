<script lang="ts">
  import type { ToolOutputSchemaState } from '$lib/admin/tool-output-schema';

  let { outputSchema }: { outputSchema: ToolOutputSchemaState } = $props();

  function sortedJsonValue(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(sortedJsonValue);
    if (value !== null && typeof value === 'object') {
      return Object.fromEntries(
        Object.entries(value)
          .sort(([left], [right]) => left.localeCompare(right))
          .map(([key, item]) => [key, sortedJsonValue(item)])
      );
    }
    return value;
  }

  const formattedSchema = $derived(
    outputSchema.status === 'available'
      ? JSON.stringify(sortedJsonValue(outputSchema.schema), null, 2)
      : ''
  );
</script>

<section aria-label="Output schema" class="output-schema">
  <span class="label">Output schema</span>
  {#if outputSchema.status === 'available'}
    <details>
      <summary>Available</summary>
      <pre><code>{formattedSchema}</code></pre>
    </details>
  {:else}
    <span class="status status--warning">
      <svg class="warning-icon" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
        <path d="M10 2.4 18.2 17H1.8L10 2.4Z" />
        <path d="M10 7v4.5M10 14.3v.2" />
      </svg>
      <span>Not declared</span>
    </span>
  {/if}
</section>

<style>
  .output-schema { align-items: baseline; display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.875rem; }
  .label { color: #37352f; font-size: 0.8rem; font-weight: 600; }
  details { max-width: 100%; width: 100%; }
  summary, .status { color: #787774; font-size: 0.8rem; }
  summary { cursor: pointer; width: fit-content; }
  .status--warning { align-items: center; color: #9a6700; display: inline-flex; font-weight: 600; gap: 0.25rem; }
  .warning-icon { fill: #fff4ce; height: 1rem; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.5; width: 1rem; }
  pre { background: #f7f6f3; border: 1px solid #e3e2df; border-radius: 6px; margin: 0.4rem 0 0; max-height: 16rem; max-width: 100%; overflow: auto; padding: 0.65rem; }
  pre code { background: transparent; border: 0; border-radius: 0; display: block; padding: 0; white-space: pre; }
</style>
