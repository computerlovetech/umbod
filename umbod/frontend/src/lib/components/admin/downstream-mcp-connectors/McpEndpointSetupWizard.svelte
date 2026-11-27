<script lang="ts">
  import { tick } from 'svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import Disclosure from '#lib/components/shared/Disclosure.svelte';
  import SetupProgress from '#lib/components/admin/shared/SetupProgress.svelte';
  import ModalShell from '#lib/components/shared/ModalShell.svelte';
  import { nativeDialog } from '#lib/components/shared/dialogs/native-dialog.js';
  import TextField from '#lib/components/shared/TextField.svelte';
  import ConnectorIcon from '../connectors/ConnectorIcon.svelte';
  import { connectorSetupSteps } from '../connectors/connector-setup-steps.js';
  import { registryEndpointKey, registryServerKey, type McpEndpointSetupState, type McpSetupMode } from './mcp-endpoint-setup-state.svelte';

  let { state, close, onbacktotype }: {
    state: McpEndpointSetupState;
    close: () => void;
    onbacktotype?: () => void;
  } = $props();

  const id = $props.id();
  const includesType = $derived(Boolean(onbacktotype));
  const steps = $derived(connectorSetupSteps('mcp', includesType));
  const labels: Record<McpSetupMode, string> = {
    none: 'No credentials',
    personal: 'Personal sign-in',
    static_bearer: 'Shared token'
  };
  const modeDescriptions: Record<McpSetupMode, string> = {
    none: 'Umbod won’t send a token.',
    personal: 'Each person signs in with their own account.',
    static_bearer: 'Use one token for everyone who uses this connector.'
  };

  function dismiss(): void {
    state.dispose();
    close();
  }

  function backToType(): void {
    const returnToPicker = onbacktotype;
    dismiss();
    returnToPicker?.();
  }

  function attachDialog(dialog: HTMLDialogElement): () => void {
    const focusTarget = state.step === 'access' ? '[data-access-heading]' : '[data-dialog-title]';
    const detach = nativeDialog(dismiss, () => true, focusTarget)(dialog);
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

{#snippet registryLogo(title: string, icon: string | undefined, large: boolean)}
  <span class={['registry-logo', large && 'registry-logo-large']} aria-hidden="true">
    <ConnectorIcon label={title} size={large ? 'medium' : 'small'} />
    {#if icon}
      {#key icon}
        <img src={icon} alt="" crossorigin="anonymous" referrerpolicy="no-referrer" loading={large ? 'eager' : 'lazy'} onerror={(event) => { event.currentTarget.setAttribute('hidden', ''); }} />
      {/key}
    {/if}
  </span>
{/snippet}

<ModalShell title="Add MCP connector" titleId={`${id}-title`} close={dismiss} dialogAttachment={attachDialog} --modal-title-focus-outline="none" --modal-overflow="auto" --modal-width="39rem" --modal-background="linear-gradient(135deg, var(--admin-accent-soft), var(--admin-panel) 17rem)" --admin-radius-panel="24px">
  <SetupProgress {steps} current={state.progress + Number(includesType)} />

  <div class="content" class:registry-search={state.step === 'search'}>
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
      {#if includesType}
        <div class="actions"><Button type="button" variant="soft" onclick={backToType}>Back</Button></div>
      {/if}
    {:else if state.step === 'search'}
      <h3>Search official MCP Registry</h3>
      <form onsubmit={submitSearch} class="search-form">
        <TextField id={`${id}-search`} label="Server name" name="term" placeholder="e.g. Svelte" value={state.term} oninput={updateSearch} autocomplete="off" {@attach focusOnEntry} />
        <Button type="submit" disabled={!state.canSearch} aria-disabled={state.searchStatus === 'loading' || undefined}>Search</Button>
      </form>
      <div class={state.hasSearched ? 'registry-results-viewport' : 'sr-only'}>
        <div class="stack">
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
                    {@render registryLogo(server.title, server.icons?.[0], false)}
                    <span class="registry-result-copy">
                      <strong>{server.title}</strong>
                      <small>{server.name} · {server.version}</small>
                    </span>
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
            <div><Button variant="secondary" onclick={(event) => moveFocus(event, state.retrySearch, '[name="term"]')}>Retry search</Button></div>
          {:else if state.hasMore}
            <div><Button variant="secondary" aria-disabled={state.searchStatus === 'loading'} onclick={loadMore}>Load more</Button></div>
          {/if}
        </div>
      </div>
      <div class="actions">
        <Button variant="soft" onclick={goBack}>Back</Button>
        <Button disabled={!state.selected} onclick={state.review}>Next</Button>
      </div>
    {:else if state.step === 'review' && state.selected}
      <div class="registry-profile">
        {@render registryLogo(state.selected.title, state.selected.icons?.[0], true)}
        <div>
          <h3 class="registry-title" tabindex="-1" {@attach focusOnEntry}>{state.selected.title}</h3>
          <p class="registry-meta">{state.selected.name} · {state.selected.version}</p>
        </div>
      </div>
      {#if state.selected.description}<p class="registry-description">{state.selected.description}</p>{/if}
      {#snippet endpointSummary(endpoint: { url: string; required_headers: readonly string[] })}
        <code>{endpoint.url}</code>
        {#if endpoint.required_headers.length}<span class="headers">Required headers: {endpoint.required_headers.join(', ')}</span>{/if}
      {/snippet}
      {#if state.selected.endpoints.length === 1}
        <dl class="endpoint-plate">
          <dt>Registry endpoint</dt>
          <dd>{@render endpointSummary(state.selected.endpoints[0])}</dd>
        </dl>
      {:else}
        <fieldset>
          <legend>Choose an endpoint</legend>
          {#each state.selected.endpoints as endpoint (registryEndpointKey(endpoint))}
            <label class="endpoint-choice">
              <input type="radio" name={`${id}-registry-endpoint`} checked={state.registryEndpoint === endpoint} onchange={() => state.selectEndpoint(endpoint)} />
              <span>{@render endpointSummary(endpoint)}</span>
            </label>
          {/each}
        </fieldset>
      {/if}
      <div class="actions">
        <Button variant="soft" onclick={state.back}>Back</Button>
        <Button disabled={!state.registryEndpoint} onclick={state.checkAccess}>Next</Button>
      </div>
    {:else if state.step === 'manual'}
      <h3>Enter URL manually</h3>
      <form class="stack" onsubmit={submitCheck}>
        <TextField id={`${id}-url`} label="MCP endpoint URL" name="endpointUrl" value={state.manualUrl} oninput={updateUrl} inputmode="url" placeholder="https://mcp.example.com/mcp" autocomplete="off" aria-invalid={Boolean(state.manualUrl && !state.canCheckManual) || undefined} aria-describedby={state.manualUrl && !state.canCheckManual ? `${id}-url-error` : undefined} {@attach focusOnEntry} />
        {#if state.manualUrl && !state.canCheckManual}<p id={`${id}-url-error`}>Enter an HTTPS URL or a local loopback HTTP URL without embedded credentials or a fragment.</p>{/if}
        <div class="actions">
          <Button variant="soft" onclick={goBack}>Back</Button>
          <Button type="submit" disabled={!state.canCheckManual}>Next</Button>
        </div>
      </form>
    {:else if state.step === 'access'}
      <h3 tabindex="-1" data-access-heading {@attach focusOnEntry}>How should Umbod connect?</h3>
      <p class="access-endpoint">{state.endpointUrl}</p>
      <div class="stack evidence" role="status">
        {#if state.access?.kind === 'checking'}
          <p class="checking"><span class="activity" aria-hidden="true"></span>Checking endpoint access…</p>
        {:else if state.access}
          {#if state.anonymousResult === 'anonymous_initialization_succeeded'}
            <div><strong>Server responded without credentials</strong><p>Tool access wasn’t checked.</p></div>
          {:else if state.anonymousResult === 'anonymous_access_rejected'}
            <p>The server rejected the initial connection without credentials.</p>
          {:else if state.access.kind === 'unsupported'}
            <p>This URL can be configured manually. Access checks require HTTPS without a query string.</p>
          {:else if state.access.kind === 'unavailable'}
            <p>The access check was unavailable.</p>
          {:else}
            <p>The access check did not determine whether the endpoint accepts anonymous initialization.</p>
          {/if}
        {/if}
      </div>
      {#snippet accessChoice(mode: McpSetupMode, status: string)}
        <label class="access-choice">
          <input type="radio" name={`${id}-access-method`} checked={state.selectedMode === mode} onchange={() => state.selectMode(mode)} aria-labelledby={`${id}-${mode}-label`} aria-describedby={status ? `${id}-${mode}-description ${id}-${mode}-status` : `${id}-${mode}-description`} />
          <span>
            <span class="access-choice-title">
              <strong id={`${id}-${mode}-label`}>{labels[mode]}</strong>
              {#if status}<span class="access-status" id={`${id}-${mode}-status`}>{status}</span>{/if}
            </span>
            <small id={`${id}-${mode}-description`}>{modeDescriptions[mode]}</small>
          </span>
        </label>
      {/snippet}
      {#if state.standardModes.length}
        <fieldset class="access-methods">
          <legend>Access method</legend>
          {#each state.standardModes as mode (mode)}
            {@render accessChoice(mode, '')}
          {/each}
          {#if state.unverifiedModes.length}
            <div class="unverified-access">
              <Disclosure expanded={state.overrideEnabled} onOpenChange={state.setOverride}>
                {#snippet label()}Unverified access methods{/snippet}
                {#if state.overrideEnabled}
                  <div class="unverified-choices">
                    {#each state.unverifiedModes as mode (mode)}
                      {@render accessChoice(mode, mode === 'personal' ? 'OAuth not confirmed' : 'Connection not verified')}
                    {/each}
                  </div>
                {/if}
              </Disclosure>
            </div>
          {/if}
        </fieldset>
      {/if}
      {#if state.uncertainAccess && state.canProbeEndpoint}
        <div><Button variant="secondary" onclick={(event) => moveFocus(event, state.checkAccess, '[data-access-heading]')}>Retry check</Button></div>
      {/if}
      <div class="actions">
        <Button variant="soft" onclick={state.back}>Back</Button>
        <Button disabled={!state.selectedMode} onclick={state.configure}>Next: Configure</Button>
      </div>
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
  .access-endpoint { color: var(--admin-muted); font: .8125rem/1.5 var(--admin-mono); }
  .access-methods { display: grid; gap: .5rem; margin: 0; padding: 0; border: 0; min-width: 0; }
  .access-methods legend { margin-bottom: .375rem; }
  .access-choice { display: flex; align-items: baseline; gap: .5rem; padding: .625rem .75rem; border: 1px solid var(--admin-border); border-radius: 10px; background: var(--admin-panel); cursor: pointer; }
  .access-choice:has(input:checked) { border-color: var(--admin-accent); background: var(--admin-accent-soft); }
  .unverified-access { --disclosure-trigger-padding: .375rem .125rem; --disclosure-trigger-width: fit-content; color: var(--admin-accent); font-size: .875rem; font-weight: 650; }
  .unverified-choices { display: grid; gap: .5rem; margin-block-start: .25rem; }
  .access-choice-title { display: flex; align-items: baseline; flex-wrap: wrap; gap: .375rem; }
  .access-status { color: var(--admin-muted); background: var(--admin-soft); border-radius: 6px; padding: .0625rem .375rem; font-size: .75rem; font-weight: 650; }
  .access-choice input { accent-color: var(--admin-accent); }
  .access-choice small, .evidence strong + p { display: block; color: var(--admin-muted); font-size: .8125rem; }
  .evidence { padding: .875rem 1rem; border: 1px solid var(--admin-accent-border); border-radius: var(--admin-radius-panel); background: var(--admin-accent-soft); }
  @media (max-width: 30rem) {
    .tiles :global(.setup-tile) { gap: .45rem; border-radius: 14px; }
    .tile-arrow { display: none; }
  }
  .actions { display: flex; align-items: center; justify-content: space-between; gap: .5rem; padding-block-start: .875rem; border-top: 1px solid var(--admin-border); }
  .search-form { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: .5rem; }
  :global(dialog):has(> .registry-search) {
    --registry-search-top: max(1rem, calc((100dvh - 34rem) / 2));
    inset-block: var(--registry-search-top) auto;
    margin-block: 0;
    max-block-size: calc(100dvh - var(--registry-search-top) - 1rem);
  }
  @media (max-width: 30rem) {
    :global(dialog):has(> .registry-search) { border-radius: 12px; }
  }
  .registry-results-viewport { box-sizing: border-box; block-size: clamp(7rem, calc(100dvh - 25rem), 16rem); overflow-y: auto; scrollbar-gutter: stable; padding: .25rem; }
  .servers { display: grid; gap: .5rem; list-style: none; padding: 0; margin: 0; }
  .servers :global(.registry-result) { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: .625rem; width: 100%; text-align: start; white-space: normal; overflow-wrap: anywhere; }
  .registry-result-copy { display: grid; gap: .125rem; min-width: 0; }
  .registry-result-copy small { color: var(--admin-muted); font-size: .8125rem; }
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
  .headers { color: var(--admin-muted); font-size: .85rem; }
  fieldset { min-inline-size: 0; margin: 0; padding: .75rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); }
  .registry-profile { display: flex; align-items: center; gap: .75rem; min-width: 0; }
  .registry-logo { position: relative; display: grid; place-items: center; width: 2rem; height: 2rem; flex: none; border: 1px solid var(--admin-accent-border); border-radius: 8px; background: var(--admin-panel); }
  .registry-logo-large { width: 2.75rem; height: 2.75rem; border-radius: 12px; }
  .registry-logo img:not([hidden]) { position: absolute; inset: 0; width: 100%; height: 100%; padding: .25rem; box-sizing: border-box; object-fit: contain; border-radius: inherit; background: var(--admin-panel); }
  .registry-title:focus { outline: none; }
  .registry-meta, .registry-description { color: var(--admin-muted); line-height: 1.5; }
  .registry-meta { font-size: .8125rem; }
  .endpoint-plate { display: grid; gap: .3rem; margin: 0; padding: .75rem 1rem; border: 1px solid var(--admin-accent-border); border-radius: 12px; background: var(--admin-accent-soft); }
  .endpoint-plate dt, legend { font-size: .8125rem; font-weight: 650; }
  .endpoint-plate dd { margin: 0; }
  .endpoint-plate code, .endpoint-choice code { display: block; color: var(--admin-accent); font: .8125rem/1.5 var(--admin-mono); overflow-wrap: anywhere; }
  .headers { display: block; margin-top: .25rem; overflow-wrap: anywhere; }
  .endpoint-choice { display: flex; gap: .5rem; align-items: baseline; cursor: pointer; }
  .endpoint-choice + .endpoint-choice { margin-block-start: .75rem; }
</style>
