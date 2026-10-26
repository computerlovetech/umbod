<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { ToolParameter, ToolOutputSchemaState } from '$lib/components/shared/tools/presentation';
  import ToolCardLayout from '$lib/components/shared/tools/ToolCard.svelte';
  import ToolDescription from '$lib/components/shared/tools/ToolDescription.svelte';
  import ToolParameterDetails from '$lib/components/shared/tools/ToolParameterDetails.svelte';
  import ToolOutputSchemaDetails from '$lib/components/shared/tools/ToolOutputSchemaDetails.svelte';

  let { title, name, description: descriptionText, parameters: toolParameters, inputSchema, outputSchema: toolOutputSchema = { status: 'not-declared' }, controls }: {
    title: string;
    name: string;
    description: string;
    parameters: ToolParameter[];
    inputSchema?: Record<string, unknown>;
    outputSchema?: ToolOutputSchemaState;
    controls?: Snippet;
  } = $props();
</script>

<ToolCardLayout {title} {name} {controls}>
  {#snippet description()}
    <ToolDescription description={descriptionText} />
  {/snippet}
  {#snippet parameters()}
    <ToolParameterDetails parameters={toolParameters} {inputSchema} />
  {/snippet}
  {#snippet outputSchema()}
    <ToolOutputSchemaDetails outputSchema={toolOutputSchema} />
  {/snippet}
</ToolCardLayout>
