<script lang="ts">
  import type { ConnectorKind } from '$lib/admin/capability-descriptions';
  import AdminModalShell from '$lib/components/admin/shared/AdminModalShell.svelte';
  import CapabilityDescriptionOverrideForm from './CapabilityDescriptionOverrideForm.svelte';

  let { kind, connectorId, close }: { kind: ConnectorKind; connectorId: string; close: () => void } = $props();
</script>

<AdminModalShell title="Edit capability description" titleId={`capability-description-modal-${kind}-${connectorId}`} {close}>
  <CapabilityDescriptionOverrideForm {kind} {connectorId} />
</AdminModalShell>
