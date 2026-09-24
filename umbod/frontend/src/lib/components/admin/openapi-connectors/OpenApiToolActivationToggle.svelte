<script lang="ts">
  import type { OpenApiToolActivationStatus } from '$lib/admin/openapi-connectors';
  import AdminToggle from '$lib/components/admin/shared/AdminToggle.svelte';

  let {
    operationId,
    activationStatus,
    disabled = false,
    onActivationChange
  }: {
    operationId: string;
    activationStatus: OpenApiToolActivationStatus;
    disabled?: boolean;
    onActivationChange: (operationId: string, activationStatus: OpenApiToolActivationStatus) => void;
  } = $props();

  function changeActivation(event: Event): void {
    const enabled = (event.currentTarget as HTMLInputElement).checked;
    onActivationChange(operationId, enabled ? 'enabled' : 'disabled');
  }
</script>

<AdminToggle checked={activationStatus === 'enabled'} ariaLabel={`${operationId} activation`} {disabled} onchange={changeActivation} />
