<script lang="ts">
  import { enhance } from '$app/forms';
  import type { HTMLButtonAttributes } from 'svelte/elements';
  import LoadingButton from '$lib/components/admin/shared/LoadingButton.svelte';
  import { useToast } from '$lib/components/feedback';
  import { FormPendingState } from '$lib/components/admin/shared/form-pending-state.svelte';

  type PublicationAction = 'publish' | 'unpublish';
  type PublicationActionLabel = 'Publish' | 'Unpublish';

  type Props = {
    connectorId: string;
    connectorName: string;
    action: PublicationAction;
    disabled?: boolean;
    title?: string;
    role?: HTMLButtonAttributes['role'];
    onrequest: (event: MouseEvent, connectorName: string, actionLabel: PublicationActionLabel) => void;
  };

  let { connectorId, connectorName, action, disabled = false, title, role, onrequest }: Props = $props();

  const pendingState = new FormPendingState();
  const toast = useToast();
  const actionLabel = $derived<PublicationActionLabel>(action === 'publish' ? 'Publish' : 'Unpublish');
  const pendingKey = $derived(`${action}:${connectorId}`);

  function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }
</script>

<form method="POST" action={`?/${action}`} use:enhance={() => {
  pendingState.start(pendingKey);
  return async ({ update, result }) => {
    try {
      if (result.type === 'redirect') {
        toast.success(`${connectorName} ${action === 'publish' ? 'published' : 'unpublished'}`);
      } else if (result.type === 'success') {
        if (!isRecord(result.data) || (result.data.status !== 'published' && result.data.status !== 'unpublished' && result.data.status !== 'failed')) {
          throw new Error('Invalid connector publication result');
        }
        if (result.data.status === 'failed') {
          if (typeof result.data.errorMessage !== 'string') throw new Error('Invalid connector publication failure result');
          toast.error(result.data.errorMessage);
        } else {
          toast.success(typeof result.data.successMessage === 'string' ? result.data.successMessage : `${connectorName} ${result.data.status}`);
        }
      } else if (result.type === 'failure') {
        if (!isRecord(result.data) || typeof result.data.message !== 'string') throw new Error('Invalid connector publication failure result');
        toast.error(result.data.message);
      } else {
        throw new Error('Unexpected connector publication result');
      }
      await update();
    } finally {
      pendingState.stop(pendingKey);
    }
  };
}}>
  <input type="hidden" name="connectorId" value={connectorId} />
  <LoadingButton
    type="button"
    label={actionLabel}
    onclick={(event) => onrequest(event, connectorName, actionLabel)}
    loadingLabel={`${actionLabel}ing...`}
    loading={pendingState.isPending(pendingKey)}
    variant="secondary"
    {disabled}
    {title}
    {role}
  />
</form>
