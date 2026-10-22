<script lang="ts">
  import SharedMcpSetupGuide from '$lib/components/shared/mcp-setup/McpSetupGuide.svelte';

  type Props = { mcpEndpoint: string };
  let { mcpEndpoint }: Props = $props();
</script>

<SharedMcpSetupGuide {mcpEndpoint} />
