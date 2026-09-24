<script lang="ts">
  import { enhance } from '$app/forms';
  import type { ConnectorConfigurationField } from '$lib/admin/connectors';
  import AdminConfigurationField from '$lib/components/admin/shared/AdminConfigurationField.svelte';
  import LoadingButton from '$lib/components/admin/shared/LoadingButton.svelte';
  import { FormPendingState } from '$lib/components/admin/shared/form-pending-state.svelte';
  import { useToast } from '$lib/components/feedback';
  import { ConnectorConfigurationFormState } from './connector-configuration-form-state.svelte';

  type Connector = {
    id: string;
    name: string;
  };

  type FormData = {
    status?: string;
    connectorId?: string;
    errorMessage?: string;
    successMessage?: string;
    values?: Record<string, string>;
  } | null;

  let {
    connector,
    fields,
    form = null,
    action,
    checkAction = '?/checkConfiguration',
    submitConnectorId = false,
    onsaved
  }: {
    connector: Connector;
    fields: ConnectorConfigurationField[];
    form?: FormData;
    action?: string;
    checkAction?: string;
    submitConnectorId?: boolean;
    onsaved?: () => void;
  } = $props();

  let formElement: HTMLFormElement | undefined;

  const pendingState = new FormPendingState();
  const toast = useToast();
  const state = new ConnectorConfigurationFormState();
  const saveConfigurationKey = $derived(`save-configuration:${connector.id}`);
  const checkConfigurationKey = $derived(`check-configuration:${connector.id}`);
  const saveConfigurationPending = $derived(pendingState.isPending(saveConfigurationKey));
  const checkConfigurationPending = $derived(pendingState.isPending(checkConfigurationKey));
  const feedback = $derived(state.feedback(form?.status, form?.errorMessage));
  const secretFieldNames = $derived(fields.filter((field) => field.inputType === 'password').map((field) => field.name));
  const hasRequiredUnsupportedFields = $derived(
    fields.some((field) => field.required && field.unsupported)
  );

  $effect(() => {
    if (formElement) {
      state.replaceCurrentSignature(configurationSignature(formElement));
    }
  });

  function configurationSignature(form: HTMLFormElement): string {
    const entries: Array<[string, string]> = [];

    for (const [key, value] of new FormData(form).entries()) {
      if (key !== 'connectorId' && !key.startsWith('__') && typeof value === 'string') {
        entries.push([key, value]);
      }
    }

    return JSON.stringify(entries.sort(([left], [right]) => left.localeCompare(right)));
  }

  function actionIsCheck(submitter: HTMLElement | null): boolean {
    return submitter instanceof HTMLButtonElement && submitter.formAction.includes('checkConfiguration');
  }

  function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  function actionStatus(result: unknown): string | null {
    if (!isRecord(result) || !isRecord(result.data) || typeof result.data.status !== 'string') {
      return null;
    }

    return result.data.status;
  }

  function updateSignature(): void {
    if (!formElement) {
      return;
    }

    state.replaceCurrentSignature(configurationSignature(formElement));
  }
</script>

<section class="configuration admin-panel" aria-labelledby="connector-configuration-title">
  <div class="section-heading">
    <p class="eyebrow">Connector action</p>
    <h2 id="connector-configuration-title">Configure connector</h2>
  </div>

  <form
    bind:this={formElement}
    method="POST"
    {action}
    aria-label={`${connector.name} configuration`}
    oninput={updateSignature}
    use:enhance={({ submitter }) => {
      const checkingConfiguration = actionIsCheck(submitter);
      const pendingKey = checkingConfiguration ? checkConfigurationKey : saveConfigurationKey;
      const submittedSignature = formElement ? configurationSignature(formElement) : '';
      pendingState.start(pendingKey);

      return async ({ update, result }) => {
        await update({ reset: false });

        const status = actionStatus(result);
        if (checkingConfiguration && status === 'check-valid') {
          state.markChecked(submittedSignature);
        }
        if (!checkingConfiguration && status === 'saved') {
          toast.success(form?.successMessage ?? `${connector.name} configuration saved`);
          onsaved?.();
        } else if (!checkingConfiguration && status === 'failed') {
          toast.error(form?.errorMessage ?? 'Configuration could not be saved');
        }

        pendingState.stop(pendingKey);
      };
    }}
  >
    <p class={["feedback-message", `feedback-message--${feedback.tone}`]}>{feedback.message}</p>

    <input type="hidden" name="__secret_fields" value={secretFieldNames.join(',')} />
    {#if submitConnectorId}
      <input type="hidden" name="connectorId" value={connector.id} />
    {/if}

    {#each fields as field (field.name)}
      <AdminConfigurationField
        id={field.name}
        name={field.name}
        label={field.label}
        type={field.inputType}
        required={field.required}
        configuredSecret={field.inputType === 'password' && field.secretConfigured}
        unsupported={field.unsupported}
        value={field.inputType === 'password' ? '' : (form?.values?.[field.name] ?? field.value)}
      />
    {/each}

    {#if hasRequiredUnsupportedFields}
      <p class="unsupported">Required fields are not supported in this interface.</p>
    {/if}

    <div class="form-actions">
      <LoadingButton
        type="submit"
        label="Check configuration"
        loadingLabel="Checking configuration..."
        loading={checkConfigurationPending}
        disabled={hasRequiredUnsupportedFields}
        variant="secondary"
        formaction={checkAction}
      />
      <LoadingButton
        type="submit"
        label="Save configuration"
        loadingLabel="Saving configuration..."
        loading={saveConfigurationPending}
        disabled={hasRequiredUnsupportedFields || !state.saveEnabled}
      />
    </div>
  </form>
</section>

<style>
  .configuration {
    max-width: 64rem;
  }

  .section-heading {
    display: grid;
    gap: 6px;
  }

  h2 {
    color: #37352f;
    font-size: 18px;
    font-weight: 650;
    line-height: 1.3;
    margin: 0;
  }

  .eyebrow {
    color: #787774;
    font-size: 12px;
    font-weight: 650;
    letter-spacing: 0.12em;
    line-height: 1.4;
    margin: 0;
    text-transform: uppercase;
  }

  form {
    display: grid;
    gap: 16px;
    margin-top: 16px;
    max-width: 42rem;
  }

  .unsupported,
  .feedback-message {
    border-radius: 8px;
    font-size: 13px;
    line-height: 1.5;
    margin: 0;
  }

  .feedback-message {
    padding: 9px 10px;
  }

  .feedback-message--success {
    background: #edf7ed;
    border: 1px solid #d3e8d3;
    color: #2f6f3e;
  }

  .feedback-message--warning {
    background: #fbf3db;
    border: 1px solid #ead9a9;
    color: #7a5d16;
  }

  .feedback-message--error {
    background: #fff6f6;
    border: 1px solid #f0c7c7;
    color: #8f3232;
  }

  .feedback-message--muted {
    background: #f7f6f3;
    border: 1px solid #e9e9e7;
    color: #787774;
  }

  .form-actions {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .unsupported {
    background: #fbf3db;
    border: 1px solid #ead9a9;
    color: #7a5d16;
    padding: 9px 10px;
  }

</style>
