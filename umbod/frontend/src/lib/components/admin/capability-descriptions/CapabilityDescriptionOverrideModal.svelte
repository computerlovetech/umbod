<script lang="ts">
  import type { ConnectorKind } from '$lib/admin/capability-descriptions';
  import ModalShell from '$lib/components/shared/ModalShell.svelte';
  import CapabilityDescriptionOverrideForm from './CapabilityDescriptionOverrideForm.svelte';

  let { kind, connectorId, close }: { kind: ConnectorKind; connectorId: string; close: () => void } = $props();
</script>

<ModalShell title="Edit capability description" titleId={`capability-description-modal-${kind}-${connectorId}`} {close}>
  <CapabilityDescriptionOverrideForm {kind} {connectorId} />
</ModalShell>
