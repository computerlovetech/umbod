<script lang="ts">
  import type { DownstreamMcpTool } from '$lib/admin/downstream-mcp-connectors';
  import AdminToggle from '$lib/components/admin/shared/AdminToggle.svelte';

  let {
    tool,
    disabled = false,
    onActivationChange
  }: {
    tool: DownstreamMcpTool;
    disabled?: boolean;
    onActivationChange: (downstreamName: string, activationStatus: DownstreamMcpTool['activation_status']) => void;
  } = $props();

  function changeActivation(event: Event): void {
    const enabled = (event.currentTarget as HTMLInputElement).checked;
    onActivationChange(tool.name, enabled ? 'enabled' : 'disabled');
  }
</script>

<AdminToggle checked={tool.activation_status === 'enabled'} ariaLabel={`${tool.name} activation`} {disabled} onchange={changeActivation} />
