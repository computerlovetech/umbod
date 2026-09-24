<script lang="ts">
  import type { InvocationPolicyMode } from '$lib/admin/invocation-policy';
  import Select from '$lib/components/admin/shared/Select.svelte';
  import type { SelectOption } from '$lib/components/admin/shared/select-state.svelte';

  const invocationModeOptions: SelectOption[] = [
    { value: 'direct', label: 'Direct' },
    { value: 'ask', label: 'Ask for approval' }
  ];

  let { toolId, mode, disabled = false, conflict = false, onchange }: {
    toolId: string;
    mode: InvocationPolicyMode;
    disabled?: boolean;
    conflict?: boolean;
    onchange: (toolId: string, mode: InvocationPolicyMode) => void;
  } = $props();

  function change(value: string): void {
    if (value === 'direct' || value === 'ask') onchange(toolId, value);
  }
</script>

<div class="policy-control">
  <Select options={invocationModeOptions} label="Invocation" value={mode} {disabled} compact id={`invocation-${toolId}`} onchange={change} />
  {#if conflict}<span class="conflict" role="alert">Policy changed by another administrator; review and save again</span>{/if}
</div>

<style>
  .policy-control { display: grid; gap: 0.3rem; min-width: 12rem; }
  .conflict { color: #9f2d20; font-size: 0.75rem; }
</style>
