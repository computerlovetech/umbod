<script lang="ts">
  import { onDestroy, tick } from 'svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import SetupProgress from '#lib/components/admin/shared/SetupProgress.svelte';
  import ModalShell from '#lib/components/shared/ModalShell.svelte';
  import { nativeDialog } from '#lib/components/shared/dialogs/native-dialog.js';
  import TextField from '#lib/components/shared/TextField.svelte';
  import { McpEndpointSetupState, registryEndpointKey, registryServerKey, type McpEndpointSetupApi, type McpSetupDraft, type McpSetupMode } from './mcp-endpoint-setup-state.svelte';

  let { api, personalAvailable, close, complete, accessLost }: {
    api: McpEndpointSetupApi;
    personalAvailable: boolean;
    close: () => void;
    complete: (mode: McpSetupMode, draft: McpSetupDraft) => void;
    accessLost: () => void;
  } = $props();

  const id = $props.id();
  const state = new McpEndpointSetupState({
    api: () => api,
    personalAvailable: () => personalAvailable,
    complete: (mode, draft) => complete(mode, draft),
    accessLost: () => accessLost()
  });
  const steps = ['Source', 'Endpoint', 'Access', 'Configure'];
  const labels: Record<McpSetupMode, string> = {
    none: 'Continue without credentials',
    personal: 'Set up personal sign-in',
    static_bearer: 'Use a shared static token'
  };

  onDestroy(state.dispose);

  function dismiss(): void {
    state.dispose();
    close();
  }

  function attachDialog(dialog: HTMLDialogElement): () => void {
    const detach = nativeDialog(dismiss, () => true, '[data-dialog-title]')(dialog);
    const wrapTab = (event: KeyboardEvent): void => {
      if (event.key !== 'Tab' || event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
      const buttons = [...dialog.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')];
      const first = buttons[0];
      const last = buttons.at(-1);
      const focused = dialog.ownerDocument.activeElement;
      const title = dialog.querySelector('[data-dialog-title]');
      const target = event.shiftKey && (focused === first || focused === title) ? last : !event.shiftKey && focused === last ? first : undefined;
      if (!target) return;
      event.preventDefault();
      target.focus();
    };
    dialog.addEventListener('keydown', wrapTab);
    return (): void => {
      dialog.removeEventListener('keydown', wrapTab);
      detach?.();
    };
  }

  function focusOnEntry(element: HTMLElement): void {
    void tick().then(() => {
      if (element.isConnected && element.closest('dialog[open]')) element.focus();
    });
  }

  function moveFocus(event: MouseEvent, command: () => void, selector: string): void {
    const dialog = event.currentTarget instanceof HTMLElement ? event.currentTarget.closest('dialog') : null;
    command();
    void tick().then(() => dialog?.querySelector<HTMLElement>(selector)?.focus());
  }

  function goBack(event: MouseEvent): void {
    const dialog = event.currentTarget instanceof HTMLElement ? event.currentTarget.closest('dialog') : null;
    state.back();
    if (state.step === 'source') dialog?.querySelector<HTMLElement>('[data-dialog-title]')?.focus({ preventScroll: true });
  }

  function updateSearch(event: Event & { currentTarget: HTMLInputElement }): void {
    state.changeTerm(event.currentTarget.value);
  }

  async function loadMore(event: MouseEvent): Promise<void> {
    const button = event.currentTarget;
    if (!(button instanceof HTMLElement)) return;
    const dialog = button.closest('dialog');
    const count = state.servers.length;
    await state.loadMore();
    await tick();
    if (!dialog?.open || state.step !== 'search') return;
    if (document.activeElement !== button && document.activeElement !== document.body) return;
    const target = dialog.querySelectorAll<HTMLElement>('.registry-result')[count]
      ?? dialog.querySelector<HTMLElement>('[data-results-status]');
    target?.focus();
  }

  function submitSearch(event: SubmitEvent): void {
    event.preventDefault();
    void state.search();
  }

  function updateUrl(event: Event & { currentTarget: HTMLInputElement }): void {
    state.changeManualUrl(event.currentTarget.value);
  }

  function submitCheck(event: SubmitEvent): void {
    event.preventDefault();
    void state.checkAccess();
  }
</script>

<ModalShell title="Add MCP connector" titleId={`${id}-title`} close={dismiss} dialogAttachment={attachDialog} --modal-title-focus-outline="none" --modal-overflow="auto" --modal-width="39rem" --modal-background="linear-gradient(135deg, var(--admin-accent-soft), var(--admin-panel) 17rem)" --admin-radius-panel="24px">
  <SetupProgress {steps} current={state.progress} />

  <div class="content">
    {#if state.step === 'source'}
      <h3>Choose a source</h3>
      <div class="tiles">
        <Button variant="secondary" class="setup-tile registry-tile" onclick={state.openSearch}>
          <span class="tile-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg></span>
          <span class="tile-title">Search official MCP Registry</span>
          <span class="tile-arrow" aria-hidden="true">→</span>
        </Button>
        <Button variant="secondary" class="setup-tile" onclick={state.openManual}>
          <span class="tile-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="m9.5 14.5 5-5m-7 7-1 1a4 4 0 0 1-5-6l4-4a4 4 0 0 1 5.7 0m5.3 0 1-1a4 4 0 0 1 5 6l-4 4a4 4 0 0 1-5.7 0" /></svg></span>
          <span class="tile-title">Enter URL manually</span>
          <span class="tile-arrow" aria-hidden="true">→</span>
        </Button>
      </div>
    {:else if state.step === 'search'}
      <h3>Search official MCP Registry</h3>
      <form onsubmit={submitSearch} class="search-form">
        <TextField id={`${id}-search`} label="Server name" name="term" value={state.term} oninput={updateSearch} autocomplete="off" aria-describedby={state.term && !state.canSearch ? `${id}-search-hint` : undefined} {@attach focusOnEntry} />
        <Button type="submit" aria-disabled={!state.canSearch || state.searchStatus === 'loading'}>Search</Button>
      </form>
      {#if state.term && !state.canSearch}<p id={`${id}-search-hint`}>Enter between 3 and 256 characters.</p>{/if}
      <div role="status" tabindex="-1" data-results-status>
        {#if state.searchStatus === 'loading'}<span class="sr-only">Searching the registry…</span>
        {:else if state.searchStatus === 'ready' && state.servers.length === 0}<p>No servers found.</p>
        {:else if state.searchStatus === 'ready'}<p>{state.servers.length} {state.servers.length === 1 ? 'server' : 'servers'} found.</p>{/if}
      </div>
      {#if state.servers.length || state.searchStatus === 'loading'}
        <ul class="servers" aria-label="Registry results" aria-busy={state.searchStatus === 'loading'}>
          {#each state.servers as server (registryServerKey(server))}
            <li>
              <Button variant="secondary" class="registry-result" aria-pressed={state.selected === server} onclick={() => state.selectServer(server)}>
                <strong>{server.title}</strong>
                <span>{server.name} · {server.version}</span>
              </Button>
            </li>
          {/each}
          {#if state.searchStatus === 'loading'}
            {#each [1, 2] as placeholder (placeholder)}
              <li class="result-placeholder" aria-hidden="true">
                <span class="placeholder-line"></span>
                <span class="placeholder-line"></span>
              </li>
            {/each}
          {/if}
        </ul>
      {/if}
      {#if state.searchStatus === 'error'}
        <p class="admin-message admin-message--error" role="alert">Could not load results from the registry.</p>
        <Button variant="secondary" onclick={(event) => moveFocus(event, state.retrySearch, '[name="term"]')}>Retry search</Button>
      {:else if state.hasMore}
        <Button variant="secondary" aria-disabled={state.searchStatus === 'loading'} onclick={loadMore}>Load more</Button>
      {/if}
      <div class="actions">
        <Button variant="quiet" onclick={goBack}>Back</Button>
        <Button disabled={!state.selected} onclick={state.review}>Next</Button>
      </div>
    {:else if state.step === 'review' && state.selected}
      <h3 tabindex="-1" {@attach focusOnEntry}>{state.selected.title}</h3>
      <p>{state.selected.name} · {state.selected.version}</p>
      {#if state.selected.description}<p>{state.selected.description}</p>{/if}
      <fieldset>
        <legend>{state.selected.endpoints.length === 1 ? 'Registry endpoint' : 'Choose an endpoint'}</legend>
        {#each state.selected.endpoints as endpoint (registryEndpointKey(endpoint))}
          <div class="endpoint">
            {#if state.selected.endpoints.length > 1}
              <label><input type="radio" name={`${id}-registry-endpoint`} checked={state.registryEndpoint === endpoint} onchange={() => state.selectEndpoint(endpoint)} /> <span>{endpoint.url}</span></label>
            {:else}
              <p>{endpoint.url}</p>
            {/if}
            {#if endpoint.required_headers.length}<p class="headers">Required headers: {endpoint.required_headers.join(', ')}</p>{/if}
          </div>
        {/each}
      </fieldset>
      <div class="actions">
        <Button variant="quiet" onclick={state.back}>Back</Button>
        <Button disabled={!state.registryEndpoint} onclick={state.checkAccess}>Next</Button>
      </div>
    {:else if state.step === 'manual'}
      <h3>Enter URL manually</h3>
      <form class="stack" onsubmit={submitCheck}>
        <TextField id={`${id}-url`} label="MCP endpoint URL" name="endpointUrl" value={state.manualUrl} oninput={updateUrl} inputmode="url" placeholder="https://mcp.example.com/mcp" autocomplete="off" aria-invalid={Boolean(state.manualUrl && !state.canCheckManual) || undefined} aria-describedby={state.manualUrl && !state.canCheckManual ? `${id}-url-error` : undefined} {@attach focusOnEntry} />
        {#if state.manualUrl && !state.canCheckManual}<p id={`${id}-url-error`}>Enter an HTTPS URL or a local loopback HTTP URL without embedded credentials or a fragment.</p>{/if}
        <div class="actions">
          <Button variant="quiet" onclick={goBack}>Back</Button>
          <Button type="submit" disabled={!state.canCheckManual}>Next</Button>
        </div>
      </form>
    {:else if state.step === 'access'}
      <h3 tabindex="-1" data-access-heading {@attach focusOnEntry}>Endpoint access</h3>
      <p>{state.endpointUrl}</p>
      <div class="stack evidence" role="status">
        {#if state.access?.kind === 'checking'}
          <p class="checking"><span class="activity" aria-hidden="true"></span>Checking endpoint access…</p>
        {:else if state.access}
          {#if state.anonymousResult === 'anonymous_initialization_succeeded'}
            <p>The endpoint accepted MCP initialization without credentials. This does not verify tool access.</p>
          {:else if state.anonymousResult === 'anonymous_access_rejected'}
            <p>The endpoint rejected initialization without credentials.</p>
          {:else if state.access.kind === 'unsupported'}
            <p>This URL can be configured manually. Access checks require HTTPS without a query string.</p>
          {:else if state.access.kind === 'unavailable'}
            <p>The access check was unavailable.</p>
          {:else}
            <p>The access check did not determine whether the endpoint accepts anonymous initialization.</p>
          {/if}
          {#if state.oauthConfirmed}
            <p>OAuth was discovered. This does not establish whether accounts or credentials should be shared.</p>
          {:else if state.access.kind === 'result' && state.access.result.oauth.kind === 'oauth_not_confirmed'}
            <p>OAuth was not confirmed.</p>
          {/if}
        {/if}
      </div>
      <div class="actions">
        <Button variant="quiet" onclick={state.back}>Back</Button>
        {#if state.uncertainAccess && state.canProbeEndpoint}<Button variant="secondary" onclick={(event) => moveFocus(event, state.checkAccess, '[data-access-heading]')}>Retry check</Button>{/if}
        {#if state.canOverride && !state.overrideEnabled}<Button variant="secondary" onclick={(event) => moveFocus(event, state.enableOverride, '[data-manual-options]')}>Choose access manually</Button>{/if}
      </div>
      {#if state.overrideEnabled}<p tabindex="-1" data-manual-options>Choose an access method you know this endpoint supports.</p>{/if}
      {#if state.modes.length}
        <div class="actions">
          {#each state.modes as mode (mode)}
            <Button variant={mode === 'none' && !state.uncertainAccess ? 'primary' : 'secondary'} onclick={() => state.finish(mode)}>{labels[mode]}{mode === 'none' && state.uncertainAccess ? ' (unverified)' : ''}</Button>
          {/each}
        </div>
      {/if}
    {/if}
  </div>
</ModalShell>

<style>
  .content, .stack { display: grid; gap: .875rem; min-width: 0; }
  h3, p { margin: 0; overflow-wrap: anywhere; }
  h3 { font-size: 1.0625rem; letter-spacing: -.02em; }
  .tiles { display: grid; grid-template-columns: repeat(2, minmax(0, 13rem)); justify-content: center; gap: clamp(.625rem, 3vw, 1rem); margin-block: .25rem .5rem; }
  .tiles :global(.setup-tile) { position: relative; display: grid; place-content: center; justify-items: center; gap: .75rem; aspect-ratio: 1; width: 100%; height: auto; padding: .75rem; white-space: normal; text-align: center; background: var(--admin-soft); border: 1px solid var(--admin-border-strong); border-radius: 20px; }
  .tiles :global(.registry-tile) { background: var(--admin-accent-soft); border-color: var(--admin-accent-border); }
  .tiles :global(.setup-tile:hover), .tiles :global(.setup-tile:focus-visible) { background: var(--admin-accent-soft); border-color: var(--admin-accent); }
  .tile-icon { display: grid; place-items: center; width: clamp(2rem, 8vw, 3.25rem); aspect-ratio: 1; background: var(--admin-panel); border: 1px solid var(--admin-accent-border); border-radius: 30%; color: var(--admin-accent); }
  .tile-icon svg { width: 55%; }
  .tile-title { max-inline-size: 10rem; font-size: clamp(.8125rem, 2.5vw, 1rem); font-weight: 700; line-height: 1.3; }
  .tile-arrow { position: absolute; inset-inline-end: .875rem; inset-block-end: .625rem; color: var(--admin-accent); }
  .evidence { padding: .875rem 1rem; border: 1px solid var(--admin-accent-border); border-radius: var(--admin-radius-panel); background: var(--admin-accent-soft); }
  @media (max-width: 30rem) {
    .tiles :global(.setup-tile) { gap: .45rem; border-radius: 14px; }
    .tile-arrow { display: none; }
  }
  .actions { display: flex; flex-wrap: wrap; gap: .5rem; }
  .search-form { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: .5rem; }
  .servers { display: grid; gap: .5rem; list-style: none; padding: 0; margin: 0; }
  .servers :global(.registry-result) { display: grid; width: 100%; text-align: start; justify-content: start; white-space: normal; overflow-wrap: anywhere; }
  .servers :global(.registry-result[aria-pressed='true']) { background: var(--admin-accent-soft); border-color: var(--admin-accent); }
  .result-placeholder { display: grid; align-content: center; gap: .45rem; min-height: 3.35rem; padding: .625rem .75rem; background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); }
  .placeholder-line { width: 42%; height: .625rem; border-radius: 1rem; background: linear-gradient(110deg, var(--admin-accent-soft) 25%, var(--admin-panel) 48%, var(--admin-accent-soft) 68%); background-size: 250% 100%; animation: result-shimmer 1.3s linear infinite; }
  .placeholder-line + .placeholder-line { width: 64%; height: .5rem; }
  .result-placeholder:nth-child(even) .placeholder-line { animation-delay: -.15s; }
  @keyframes result-shimmer { from { background-position: 100% 0; } to { background-position: -60% 0; } }
  .activity { display: inline-block; width: .9rem; height: .9rem; flex: 0 0 auto; border-radius: 50%; border: 2px solid currentColor; border-inline-end-color: transparent; animation: search-activity .75s linear infinite; }
  .checking { display: flex; align-items: center; gap: .5rem; }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
  @keyframes search-activity { to { transform: rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) { .activity, .placeholder-line { animation: none; } }
  .servers span, .headers { color: var(--admin-muted); font-size: .85rem; }
  fieldset { min-inline-size: 0; margin: 0; padding: .75rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); }
  .endpoint + .endpoint { margin-block-start: .75rem; }
  .endpoint label { display: flex; gap: .4rem; align-items: baseline; overflow-wrap: anywhere; }
</style>
