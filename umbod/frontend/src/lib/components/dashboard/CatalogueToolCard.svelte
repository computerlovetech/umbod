<script lang="ts">
  import type { CatalogueCapability } from '$lib/dashboard/domain/schemas';
  import { mapJsonSchemaToToolParameters } from '$lib/components/shared/tools/json-schema-tool-parameters';
  import ToolCard from '$lib/components/shared/tools/ToolCard.svelte';
  import ToolDescription from '$lib/components/shared/tools/ToolDescription.svelte';
  import ToolParameterDetails from '$lib/components/shared/tools/ToolParameterDetails.svelte';
  import ToolOutputSchemaDetails from '$lib/components/shared/tools/ToolOutputSchemaDetails.svelte';

  let { capability }: { capability: Extract<CatalogueCapability, { kind: 'tool' }> } = $props();
</script>

<ToolCard title={capability.name} name={capability.key}>
  {#snippet description()}
    <ToolDescription description={capability.description} />
  {/snippet}
  {#snippet parameters()}
    <ToolParameterDetails parameters={mapJsonSchemaToToolParameters(capability.input_schema)} inputSchema={capability.input_schema} />
  {/snippet}
  {#snippet outputSchema()}
    <ToolOutputSchemaDetails outputSchema={capability.output_schema.status === 'present' ? { status: 'available', schema: capability.output_schema.schema } : { status: 'not-declared' }} />
  {/snippet}
</ToolCard>
