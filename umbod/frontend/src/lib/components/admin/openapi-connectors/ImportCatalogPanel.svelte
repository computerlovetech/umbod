<script lang="ts">
  import { enhance } from '$app/forms';
  import type { SubmitFunction } from '@sveltejs/kit';
  import { untrack } from 'svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import SecurityBoundaryNotice from './SecurityBoundaryNotice.svelte';
  import { ImportCatalogState } from './import-catalog-state.svelte';

  type ActionData = {
    status: string;
    mode: 'file' | 'url';
    message: string;
    retryable?: boolean;
    url?: string;
    approvedHosts?: string[];
  } | null | undefined;

  let { connectorId, action }: { connectorId: string; action?: ActionData } = $props();
  const state = new ImportCatalogState(
    untrack(() => (action ? { mode: action.mode, url: action.url, approvedHosts: action.approvedHosts } : undefined))
  );

  const submitUrlImport: SubmitFunction = async ({ formData, cancel }) => {
    if (!state.beginUrlSubmit()) {
      cancel();
      return;
    }
    const fetched = await state.fetchDocumentFromUrl();
    if (!fetched.ok) {
      cancel();
      state.finishSubmit();
      return;
    }
    formData.set('document', JSON.stringify(fetched.document));
    formData.delete('url');
    return async ({ update }) => {
      await update();
      state.finishSubmit();
    };
  };
</script>

<div class="import-panel">
  <div class="modes" role="group" aria-label="Import source">
    <button type="button" class:active={state.mode === 'file'} aria-pressed={state.mode === 'file'} onclick={() => state.setMode('file')}>
      File
    </button>
    <button type="button" class:active={state.mode === 'url'} aria-pressed={state.mode === 'url'} onclick={() => state.setMode('url')}>
      HTTPS URL
    </button>
  </div>
  <SecurityBoundaryNotice />
  {#if action}
    <p class="error" role="alert">{action.message}{#if action.retryable} You can retry safely.{/if}</p>
  {/if}
  {#if state.mode === 'file'}
    <form
      method="POST"
      action="?/importFile"
      enctype="multipart/form-data"
      onsubmit={(event) => {
        if (!state.beginFileSubmit()) event.preventDefault();
      }}
    >
      <input type="hidden" name="connectorId" value={connectorId} />
      <label for="catalog-file">JSON file</label>
      <input
        id="catalog-file"
        name="file"
        type="file"
        accept=".json,application/json"
        required
        onchange={(event) => state.selectFiles(event.currentTarget.files ?? [])}
        aria-describedby="file-help file-error"
        aria-invalid={state.fileError ? 'true' : undefined}
      />
      <p id="file-help" class="help">One JSON object, maximum 10 MiB. The source is sent directly and is not rendered in this page.</p>
      {#if state.fileError}
        <p id="file-error" class="error" role="alert">{state.fileError}</p>
      {/if}
      <label for="approved-host-file">Approved exact hostname</label>
      <div class="host-entry">
        <input
          id="approved-host-file"
          name="approved_hosts"
          value={state.hostInput}
          oninput={(event) => state.setHostInput(event.currentTarget.value)}
          placeholder="api.example.com"
          aria-describedby="host-help-file host-error-file"
        />
        <button type="button" onclick={state.addHost}>Add hostname</button>
      </div>
      <p id="host-help-file" class="help">Add only hosts the imported specification may call.</p>
      {#if state.hostError}
        <p id="host-error-file" class="error" role="alert">{state.hostError}</p>
      {/if}
      {#each state.approvedHosts as hostname (hostname)}
        <div class="host">
          <input type="hidden" name="approved_hosts" value={hostname} />
          <code>{hostname}</code>
          <button type="button" aria-label={`Remove ${hostname}`} onclick={() => state.removeHost(hostname)}>Remove</button>
        </div>
      {/each}
      <Button class="submit" type="submit" disabled={state.pending || Boolean(state.fileError)}>{state.pending ? 'Importing…' : 'Import file'}</Button>
    </form>
  {:else}
    <form method="POST" action="?/importDocument" use:enhance={submitUrlImport}>
      <input type="hidden" name="connectorId" value={connectorId} />
      <label for="source-url">HTTPS URL</label>
      <input
        id="source-url"
        name="url"
        type="url"
        inputmode="url"
        required
        value={state.url}
        oninput={(event) => state.setUrl(event.currentTarget.value)}
        aria-describedby="url-help url-error"
      />
      <p id="url-help" class="help">Your browser retrieves this URL, then submits the JSON document to the server with your approved hosts.</p>
      {#if state.urlError}
        <p id="url-error" class="error" role="alert">{state.urlError}</p>
      {/if}
      {#if state.fetchError}
        <p class="error" role="alert">{state.fetchError}</p>
      {/if}
      <label for="approved-host-url">Approved exact hostname</label>
      <div class="host-entry">
        <input
          id="approved-host-url"
          name="approved_hosts"
          value={state.hostInput}
          oninput={(event) => state.setHostInput(event.currentTarget.value)}
          placeholder="api.example.com"
          aria-describedby="host-help-url host-error-url"
        />
        <button type="button" onclick={state.addHost}>Add hostname</button>
      </div>
      <p id="host-help-url" class="help">Add only hosts the imported specification may call.</p>
      {#if state.hostError}
        <p id="host-error-url" class="error" role="alert">{state.hostError}</p>
      {/if}
      {#each state.approvedHosts as hostname (hostname)}
        <div class="host">
          <input type="hidden" name="approved_hosts" value={hostname} />
          <code>{hostname}</code>
          <button type="button" aria-label={`Remove ${hostname}`} onclick={() => state.removeHost(hostname)}>Remove</button>
        </div>
      {/each}
      <Button class="submit" type="submit" disabled={state.pending}>{state.pending ? 'Importing…' : 'Import URL'}</Button>
    </form>
  {/if}
</div>

<style>
  .import-panel {
    color: #37352f;
  }

  .modes {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }

  .modes button,
  .host-entry button,
  .host button {
    background: #ffffff;
    border: 1px solid #d8d8d4;
    border-radius: 6px;
    color: #37352f;
    cursor: pointer;
    font: inherit;
    font-size: 0.86rem;
    font-weight: 600;
    padding: 0.55rem 0.7rem;
  }

  .modes .active {
    background: #37352f;
    border-color: #37352f;
    color: #ffffff;
  }

  form {
    display: grid;
    gap: 0.5rem;
    margin-top: 1rem;
    max-width: 40rem;
  }

  label {
    color: #37352f;
    font-size: 0.86rem;
    font-weight: 650;
  }

  input {
    background: #ffffff;
    border: 1px solid #e9e9e7;
    border-radius: 6px;
    color: inherit;
    font: inherit;
    min-width: 0;
    padding: 0.65rem 0.7rem;
  }

  .host-entry {
    display: grid;
    gap: 0.5rem;
    grid-template-columns: 1fr auto;
  }

  .host {
    align-items: center;
    display: flex;
    gap: 0.75rem;
    justify-content: space-between;
  }

  code {
    background: #f1f1ef;
    border: 1px solid #e3e2df;
    border-radius: 999px;
    color: #37352f;
    font-size: 0.75rem;
    line-height: 1.4;
    padding: 2px 7px;
  }

  .help {
    color: #787774;
    font-size: 0.875rem;
    margin: 0 0 0.5rem;
  }

  .error {
    color: #8f3232;
    font-size: 0.875rem;
    margin: 0;
  }

  form :global(.submit) {
    justify-self: start;
    margin-top: 0.5rem;
  }

  @media (max-width: 600px) {
    .host-entry {
      grid-template-columns: 1fr;
    }

    .modes {
      align-items: stretch;
      flex-direction: column;
    }
  }
</style>
