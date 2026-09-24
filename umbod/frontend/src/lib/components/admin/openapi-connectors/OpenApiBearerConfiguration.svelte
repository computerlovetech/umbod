<script lang="ts">
  import { onMount } from 'svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import { useToast } from '$lib/components/feedback';
  import { untrack } from 'svelte';
  import AdminConfigurationField from '$lib/components/admin/shared/AdminConfigurationField.svelte';
  import { OpenApiBearerConfigurationState } from './openapi-bearer-configuration-state.svelte';

  let { connectorId }: { connectorId: string } = $props();
  const state = new OpenApiBearerConfigurationState(untrack(() => connectorId), globalThis.fetch, useToast());
  onMount(() => { void state.load(); });
</script>

<section class="panel-section" aria-labelledby="openapi-authentication-heading">
  <h3 id="openapi-authentication-heading">Bearer authentication</h3>
  {#if state.loading}
    <p role="status">Loading authentication configuration…</p>
  {:else}
    <p role="status">{state.configured ? 'Bearer token configured (********)' : 'No Bearer token configured'}</p>
    <form onsubmit={state.save}>
      <AdminConfigurationField
        id={`openapi-bearer-token-${connectorId}`}
        name="bearerToken"
        label="Bearer token"
        type="password"
        required={!state.configured}
        configuredSecret={state.configured}
        autocomplete="new-password"
        value={state.token}
        oninput={state.setToken}
      />
      <Button type="submit" disabled={state.saving}>
        {state.saving ? 'Saving…' : 'Save Bearer token'}
      </Button>
    </form>
    {#if state.message}<p role="status">{state.message}</p>{/if}
  {/if}
</section>

<style>
  form {
    display: grid;
    gap: 16px;
  }

  form :global(.admin-shared-button) {
    justify-self: start;
  }
</style>
