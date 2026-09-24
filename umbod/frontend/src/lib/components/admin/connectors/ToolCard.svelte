<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { ConnectorToolParameter } from '$lib/admin/connectors';
  import type { ToolOutputSchemaState } from '$lib/admin/tool-output-schema';
  import ToolOutputSchemaDetails from './ToolOutputSchemaDetails.svelte';
  import ToolParameterDetails from './ToolParameterDetails.svelte';

  let { title, name, description, parameters, outputSchema = { status: 'not-declared' }, controls }: {
    title: string;
    name: string;
    description: string;
    parameters: ConnectorToolParameter[];
    outputSchema?: ToolOutputSchemaState;
    controls?: Snippet;
  } = $props();
</script>

<article class="tool-card">
  <div class="tool-heading">
    <div class="tool-title">
      <h4 title={title}>{title}</h4>
      <code>{name}</code>
    </div>
    {#if controls}{@render controls()}{/if}
  </div>
  {#if description}<p>{description}</p>{/if}
  <ToolParameterDetails {parameters} />
  <ToolOutputSchemaDetails {outputSchema} />
</article>

<style>
  .tool-card { background: #fff; border: 1px solid #e9e9e7; border-radius: 10px; padding: 0.875rem; }
  .tool-heading { align-items: flex-start; display: flex; flex-wrap: wrap; gap: 0.75rem; justify-content: space-between; }
  .tool-title { align-items: flex-start; display: flex; flex: 1 1 20rem; flex-direction: column; gap: 0.5rem; min-width: 0; }
  h4 { color: #37352f; display: -webkit-box; font-size: 0.94rem; -webkit-line-clamp: 2; -webkit-box-orient: vertical; margin: 0; max-width: 100%; overflow: hidden; overflow-wrap: anywhere; }
  code { background: #f1f1ef; border: 1px solid #e3e2df; border-radius: 999px; color: #37352f; font-size: 0.75rem; line-height: 1.4; max-width: 100%; overflow-wrap: anywhere; padding: 2px 7px; white-space: normal; word-break: break-word; }
  p { color: #787774; font-size: 0.875rem; line-height: 1.55; margin: 0.7rem 0 0; overflow-wrap: anywhere; }
</style>
