<script lang="ts">
  import type { Snippet } from 'svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import { browserSubmit } from '#lib/admin/operations/browser-submit.js';
  import type { ConnectorConfigurationField } from '#lib/admin/connectors.js';
  import AdminConfigurationField from '#lib/components/admin/shared/AdminConfigurationField.svelte';
  import LoadingButton from '#lib/components/admin/shared/LoadingButton.svelte';
  import { FormPendingState } from '#lib/components/admin/shared/form-pending-state.svelte.js';
  import { useToast } from '#lib/components/feedback/index.js';
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
    fieldMessages?: Record<string, string>;
  } | null;

  let {
    connector,
    fields,
    form: submittedForm = null,
    operation = 'saveConfiguration',
    checkAction = 'checkConfiguration',
    submitConnectorId = false,
    onsaved,
    progress,
    onback
  }: {
    connector: Connector;
    fields: ConnectorConfigurationField[];
    form?: FormData;
    operation?: string;
    checkAction?: string;
    submitConnectorId?: boolean;
    onsaved?: () => void;
    progress?: Snippet<[number]>;
    onback?: () => void;
  } = $props();

  let formElement: HTMLFormElement | undefined;

  const form = $derived(submittedForm?.connectorId === connector.id ? submittedForm : null);
  const pendingState = new FormPendingState();
  const toast = useToast();
  const state = new ConnectorConfigurationFormState();
  const saveConfigurationKey = $derived(`save-configuration:${connector.id}`);
  const checkConfigurationKey = $derived(`check-configuration:${connector.id}`);
  const saveConfigurationPending = $derived(pendingState.isPending(saveConfigurationKey));
  const checkConfigurationPending = $derived(pendingState.isPending(checkConfigurationKey));
  const reviewing = $derived(Boolean(progress) && state.saveEnabled);
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
    return submitter instanceof HTMLButtonElement && submitter.dataset.operation === 'checkConfiguration';
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
  function focusHeading(heading: HTMLElement): void {
    heading.focus({ preventScroll: true });
  }
</script>

{@render progress?.(reviewing ? 3 : 2)}
<section class="configuration admin-panel" data-guided={progress ? '' : undefined} aria-labelledby="connector-configuration-title">
  <div class="section-heading">
    <p class="eyebrow">{progress ? connector.name : 'Configuration'}</p>
    {#if reviewing}
      <h2 id="connector-configuration-title" tabindex="-1" {@attach focusHeading}>Check &amp; save</h2>
    {:else if progress}
      <h2 id="connector-configuration-title" tabindex="-1" {@attach focusHeading}>Configure connector</h2>
    {:else}
      <h2 id="connector-configuration-title">{connector.name}</h2>
    {/if}
  </div>

  <form
    bind:this={formElement}
    method="POST"
    data-operation={operation}
    aria-label={`${connector.name} configuration`}
    oninput={updateSignature}
    use:browserSubmit={({ submitter, cancel, onComplete }) => {
      const checkingConfiguration = actionIsCheck(submitter);
      if (checkConfigurationPending || saveConfigurationPending || (progress && !checkingConfiguration && !reviewing)) {
        cancel();
        return;
      }
      const pendingKey = checkingConfiguration ? checkConfigurationKey : saveConfigurationKey;
      const submittedSignature = formElement ? configurationSignature(formElement) : '';
      onComplete(() => pendingState.stop(pendingKey));
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
    {#if !progress || reviewing || feedback.tone === 'error'}
      <p class={["feedback-message", `feedback-message--${feedback.tone}`]} role="status">{feedback.message}</p>
    {/if}

    <input type="hidden" name="__secret_fields" value={secretFieldNames.join(',')} />
    <input type="hidden" name="connectorId" value={connector.id} />

    <div class="configuration-fields" hidden={reviewing} inert={reviewing}>
    {#each fields as field (field.name)}
      {@const fieldError = progress && form?.status === 'check-invalid' ? form.fieldMessages?.[field.name] : undefined}
      <AdminConfigurationField
        id={field.name}
        name={field.name}
        label={field.label}
        type={field.inputType}
        required={field.required}
        readonly={Boolean(progress) && (checkConfigurationPending || saveConfigurationPending)}
        invalid={Boolean(fieldError)}
        describedBy={fieldError ? `${field.name}-error` : undefined}
        configuredSecret={field.inputType === 'password' && field.secretConfigured}
        unsupported={field.unsupported}
        value={field.inputType === 'password' ? '' : (form?.values?.[field.name] ?? field.value)}
      />
      {#if fieldError}
        <p id={`${field.name}-error`} class="feedback-message feedback-message--error">{fieldError}</p>
      {/if}
    {/each}
    </div>

    {#if hasRequiredUnsupportedFields}
      <p class="unsupported">Required fields are not supported in this interface.</p>
    {/if}

    <div class={['form-actions', progress && 'wizard-actions']}>
      {#if progress}
        <Button type="button" variant="soft" disabled={checkConfigurationPending || saveConfigurationPending} onclick={reviewing ? state.invalidateCheck : onback}>Back</Button>
      {/if}
      {#if !reviewing}
      <LoadingButton
        type="submit"
        label={progress ? 'Next' : 'Check configuration'}
        loadingLabel="Checking configuration..."
        loading={checkConfigurationPending}
        disabled={hasRequiredUnsupportedFields}
        variant={progress ? 'primary' : 'secondary'}
        data-operation={checkAction}
      />
      {/if}
      {#if !progress || reviewing}
      <LoadingButton
        type="submit"
        label={progress ? 'Save' : 'Save configuration'}
        loadingLabel="Saving configuration..."
        loading={saveConfigurationPending}
        disabled={hasRequiredUnsupportedFields || !state.saveEnabled}
      />
      {/if}
    </div>
  </form>
</section>

<style>
  .configuration {
    max-width: 64rem;
    min-height: 0;
    overflow-y: auto;
  }

  .configuration[data-guided] { background: transparent; border: 0; box-shadow: none; padding: 0; }

  .section-heading {
    display: grid;
    gap: 6px;
  }

  h2 {
    color: var(--admin-ink);
    font-size: 18px;
    font-weight: 650;
    line-height: 1.3;
    margin: 0;
  }

  .eyebrow {
    color: var(--admin-accent);
    font-family: var(--admin-mono);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.08em;
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

  .configuration-fields:not([hidden]) { display: grid; gap: 16px; }
  .wizard-actions { justify-content: space-between; }

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
    background: var(--admin-success-bg);
    border: 1px solid var(--admin-success-border);
    color: var(--admin-success-text);
  }

  .feedback-message--warning {
    background: var(--admin-warning-bg);
    border: 1px solid var(--admin-warning-border);
    color: var(--admin-warning-text);
  }

  .feedback-message--error {
    background: var(--admin-danger-bg);
    border: 1px solid var(--admin-danger-border);
    color: var(--admin-danger-text);
  }

  .feedback-message--muted {
    background: var(--admin-soft);
    border: 1px solid var(--admin-border);
    color: var(--admin-muted);
  }

  .form-actions {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    border-top: 1px solid var(--admin-border);
    padding-top: 16px;
  }

  .unsupported {
    background: var(--admin-warning-bg);
    border: 1px solid var(--admin-warning-border);
    color: var(--admin-warning-text);
    padding: 9px 10px;
  }

</style>
