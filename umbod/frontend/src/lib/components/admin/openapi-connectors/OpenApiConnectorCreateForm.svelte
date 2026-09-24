<script lang="ts">
  import { untrack } from 'svelte';
  import type { OpenApiConnectorCreateAction } from '$lib/admin/openapi-connectors';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import DelayedSpinner from '$lib/components/admin/shared/DelayedSpinner.svelte';
  import { OpenApiConnectorCreateState } from './openapi-connector-create-state.svelte';

  let { result }: { result?: OpenApiConnectorCreateAction } = $props();
  const state = new OpenApiConnectorCreateState(untrack(() => result?.displayName ?? ''));
</script>

<section class="create" aria-labelledby="create-heading">
  <div>
    <p class="eyebrow">New connector</p>
    <h2 id="create-heading">Create OpenAPI connector</h2>
  </div>
  <form method="POST" action="?/create" onsubmit={state.beginSubmit}>
    <label for="display-name">Display name</label>
    <div class="controls">
      <input
        id="display-name"
        name="displayName"
        required
        value={state.displayName}
        oninput={state.setDisplayName}
        aria-describedby={result ? 'create-error' : undefined}
        aria-invalid={result ? 'true' : undefined}
      />
      <input
        id="tool-name-prefix"
        name="toolNamePrefix"
        aria-label="Tool name prefix"
        required
        pattern="[A-Za-z0-9_-]+"
        value={state.toolNamePrefix}
        oninput={state.setToolNamePrefix}
      />
      <input
        id="capability-description"
        name="capabilityDescription"
        aria-label="Capability description"
        required
        maxlength="300"
        placeholder="What can agents accomplish with this connector?"
        bind:value={state.capabilityDescription}
      />
      <label class="override-toggle"><input type="checkbox" name="initialCapabilityOverride" checked={state.initialCapabilityOverride} onchange={state.setInitialCapabilityOverride} /> Initial capability override</label>
      {#if state.initialCapabilityOverride}<textarea name="initialCapabilityOverrideDescription" aria-label="Initial capability override description" maxlength="300" required bind:value={state.initialCapabilityOverrideDescription}></textarea>{/if}
      <Button type="submit" disabled={state.submitting}>
        {#if state.submitting}
          <DelayedSpinner active label="Creating connector" inline size="small" />
        {:else}
          Create OpenAPI connector
        {/if}
      </Button>
    </div>
    {#if result}
      <p id="create-error" class="error" role="alert">{result.message}</p>
    {/if}
  </form>
</section>

<style>
  .create {
    align-items: end;
    background: #ffffff;
    border: 1px solid #e9e9e7;
    border-radius: 10px;
    display: grid;
    gap: 1.5rem;
    grid-template-columns: minmax(180px, 0.7fr) minmax(280px, 1.3fr);
    margin-bottom: 1.5rem;
    padding: 1.25rem;
  }

  .eyebrow {
    color: #afaeab;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    margin: 0 0 0.35rem;
    text-transform: uppercase;
  }

  h2 {
    color: #37352f;
    font-size: 1.125rem;
    margin: 0;
  }

  label {
    color: #37352f;
    display: block;
    font-size: 0.8125rem;
    font-weight: 650;
    margin-bottom: 0.45rem;
  }

  .controls {
    display: flex;
    gap: 0.625rem;
  }

  .override-toggle { align-items: center; display: flex; gap: .4rem; margin: 0; }
  textarea,
  input {
    background: #ffffff;
    border: 1px solid #e9e9e7;
    border-radius: 6px;
    color: inherit;
    flex: 1;
    font: inherit;
    min-width: 0;
    padding: 0.65rem 0.7rem;
  }


  .error {
    color: #8f3232;
    font-size: 0.8125rem;
    margin: 0.5rem 0 0;
  }

  @media (max-width: 700px) {
    .create {
      grid-template-columns: 1fr;
    }

    .controls {
      align-items: stretch;
      flex-direction: column;
    }
  }
</style>
