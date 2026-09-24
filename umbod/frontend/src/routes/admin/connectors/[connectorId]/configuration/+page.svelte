<script lang="ts">
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import ConnectorConfigurationForm from '$lib/components/admin/connectors/ConnectorConfigurationForm.svelte';
  import type { ConnectorConfigurationPageData } from '$lib/admin/connectors';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';

  type ActionData = {
    status?: string;
    connectorId?: string;
    errorMessage?: string;
    successMessage?: string;
    values?: Record<string, string>;
  } | null;

  type ConnectorConfigurationAdminPageData = ConnectorConfigurationPageData & {
    accountIdentity?: HeaderAccountIdentityState;
  };

  let { data, form }: { data: ConnectorConfigurationAdminPageData; form: ActionData } = $props();

  const fallbackAccountIdentity: HeaderAccountIdentityState = { kind: 'hidden' };
</script>

<svelte:head>
  <title>Connector configuration</title>
</svelte:head>

<AdminShell activeItem="connectors" accountIdentity={data.accountIdentity ?? fallbackAccountIdentity}>
  <div class="admin-page">
    <a class="admin-back-link" href="/admin/connectors">← Connectors</a>

    {#if data.status === 'ready'}
      <p class="admin-eyebrow">Connector configuration</p>
      <h1 class="admin-title">{data.connector.name}</h1>
      <ConnectorConfigurationForm connector={data.connector} fields={data.fields} {form} />
    {:else}
      <div class="admin-message admin-message-error failure-state">
        <p>{data.message}</p>
        <a class="admin-back-link" href={data.backHref}>Back to connectors</a>
      </div>
    {/if}
  </div>
</AdminShell>

<style>
  .failure-state p {
    margin: 0 0 12px;
  }

  .failure-state .admin-back-link {
    margin-bottom: 0;
  }
</style>
