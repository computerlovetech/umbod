<script lang="ts">
  import { goto, replaceState } from '$app/navigation';
  import { page } from '$app/state';
  import Button from '../shared/Button.svelte';
  import PlusIcon from '#lib/components/shared/PlusIcon.svelte';
  import SetupProgress from '../shared/SetupProgress.svelte';
  import ModalShell from '../../shared/ModalShell.svelte';
  import { useToast } from '../../feedback/index.js';
  import { connectorSetupSteps, connectorSetupTypeStep } from './connector-setup-steps.js';
  import { connectorWorkspaceHref, connectorWorkspacePaths, isPortableRow, portableDuplicateReference, type PortableConnectorRow, type UnifiedConnectorKind, type UnifiedConnectorRow } from '#lib/admin/unified-connectors.js';
  import ConnectorIcon from './ConnectorIcon.svelte';
  import type { AddConnectorState, ConnectorSetupKind } from './add-connector-state.svelte';

  let { state: picker, unifiedRows = [], unavailableKinds = [] }: {
    state: AddConnectorState;
    unifiedRows?: readonly UnifiedConnectorRow[];
    unavailableKinds?: readonly UnifiedConnectorKind[];
  } = $props();
  const portableRows = $derived(unifiedRows.filter(isPortableRow));
  const entry = $derived(picker.entry);
  const nativeAvailable = $derived(entry?.nativeAvailable() ?? false);
  const nativeUnavailable = $derived(entry?.nativeUnavailable() ?? false);
  const disabled = $derived(entry?.disabled() ?? true);
  const pendingSetup = $derived(page.state.openConnectorSetup);

  const toast = useToast();
  const id = $props.id();
  const choices: readonly { kind: ConnectorSetupKind; label: string; description: string; icon: string }[] = [
    { kind: 'native', label: 'Native connector', description: 'Set up a connector already available in your Umbod catalog.', icon: 'catalog' },
    { kind: 'openapi', label: 'OpenAPI specification', description: 'Turn a REST API into tools using an OpenAPI JSON file or HTTPS link.', icon: 'document' },
    { kind: 'mcp', label: 'MCP server', description: 'Find a server in the official MCP Registry or enter its endpoint URL.', icon: 'link' },
    { kind: 'portable', label: 'Portable connector', description: 'Configure a portable connector that’s already been submitted.', icon: 'portable' }
  ];
  const selected = $derived(choices.find((choice) => choice.kind === picker.kind));
  const steps = $derived(selected ? connectorSetupSteps(selected.kind, true) : [connectorSetupTypeStep]);

  function clearPendingSetup(pending: ConnectorSetupKind): void {
    const { openConnectorSetup: _, ...remaining } = page.state;
    const url = new URL((page.shallow?.url ?? page.url).href);
    if (pending === 'native') url.searchParams.delete('setup');
    replaceState(url, remaining);
  }

  function resumeSetup(pending: ConnectorSetupKind | undefined, ready: boolean): (trigger: HTMLButtonElement) => void {
    return (trigger: HTMLButtonElement): void => {
      if (!pending || !ready) return;
      queueMicrotask(() => {
        const target = picker.entry;
        if (!trigger.isConnected || target?.kind !== pending || target.kind === 'portable' || target.disabled() || page.state.openConnectorSetup !== pending || (pending === 'native' && !target.nativeAvailable())) return;
        clearPendingSetup(pending);
        target.create(trigger);
        picker.close();
      });
    };
  }

  async function next(): Promise<void> {
    const selectedKind = picker.kind;
    const trigger = picker.trigger;
    const target = picker.entry;
    if (!selectedKind || !trigger || !target || picker.handingOff || disabled || (selectedKind === 'native' && !nativeAvailable)) return;
    if (selectedKind === 'portable') {
      picker.choosePortable();
      return;
    }
    if (selectedKind === target.kind) {
      target.create(trigger);
      picker.close();
      return;
    }
    picker.beginHandoff();
    try {
      const destination = new URL(connectorWorkspacePaths[selectedKind], page.url.href);
      if (selectedKind === 'native') destination.searchParams.set('setup', 'native');
      const capability = (page.shallow?.url ?? page.url).searchParams.get('capability');
      if (capability) destination.searchParams.set('capability', capability);
      await goto(destination, { state: { openConnectorSetup: selectedKind }, reset: false });
      if (picker.open && page.state.openConnectorSetup === selectedKind) clearPendingSetup(selectedKind);
      if (picker.open) toast.error('Connector setup could not be opened. Try again.');
    } catch {
      toast.error('Connector setup could not be opened. Try again.');
    } finally {
      picker.endHandoff();
    }
  }

  async function openPortable(row: PortableConnectorRow): Promise<void> {
    if (picker.handingOff) return;
    picker.beginHandoff();
    try {
      await goto(connectorWorkspaceHref(row, null), { reset: false });
      picker.close();
    } catch {
      toast.error('Could not open this portable connector. Try again.');
    } finally {
      picker.endHandoff();
    }
  }
</script>

<Button aria-label="Add connector" disabled={disabled || picker.handingOff} onclick={picker.show} {@attach picker.register} {@attach resumeSetup(pendingSetup, !disabled && pendingSetup === entry?.kind && (pendingSetup !== 'native' || nativeAvailable))}><PlusIcon />Add connector</Button>

{#if picker.open}
  <ModalShell title="Add connector" titleId={`${id}-title`} close={picker.close} closeDisabled={picker.handingOff} initialFocus="[data-dialog-title]"
    --modal-title-focus-outline="none" --modal-overflow="auto" --modal-width="40rem"
    --modal-background="linear-gradient(135deg, var(--admin-accent-soft), var(--admin-panel) 17rem)" --admin-radius-panel="24px">
    {#if picker.choosingPortable}
      <SetupProgress {steps} current={2} />
      <h3>Choose a submitted portable connector</h3>
      {#if portableRows.length}
        <ul class="submitted" aria-label="Submitted portable connectors">
          {#each portableRows as row (row.id)}
            {@const reference = portableDuplicateReference(row, portableRows)}
            <li>
              <Button variant="secondary" disabled={picker.handingOff} onclick={() => openPortable(row)}>
                <ConnectorIcon label={row.name} />
                <span class="submitted-copy"><strong>{row.name}{reference ? ` · ${reference}` : ''}</strong><span class="description">{row.description}</span></span>
              </Button>
            </li>
          {/each}
        </ul>
      {:else}
        <p role="status" class="description">{unavailableKinds.includes('portable') ? 'Could not load submitted portable connectors.' : 'No portable connectors have been submitted yet.'}</p>
      {/if}
      <footer class="choose-actions"><Button variant="soft" disabled={picker.handingOff} onclick={picker.backToType}>Back</Button></footer>
    {:else}
    {#if selected}
      <SetupProgress {steps} current={1} />
    {:else}
      <div class="initial-progress">
        <SetupProgress {steps} current={1} />
        <svg class="branch-preview" viewBox="0 0 160 30" aria-hidden="true" fill="none">
          <path d="M0 15h18c9 0 9-10 18-10h81M18 15h99M18 15c9 0 9 10 18 10h108" stroke="currentColor" stroke-dasharray="2 3" stroke-linecap="round" />
          <g stroke="currentColor" fill="var(--admin-panel)">
            <circle cx="45" cy="5" r="3.5" /><circle cx="81" cy="5" r="3.5" /><circle cx="117" cy="5" r="3.5" />
            <circle cx="45" cy="15" r="3.5" /><circle cx="81" cy="15" r="3.5" /><circle cx="117" cy="15" r="3.5" />
            <circle cx="45" cy="25" r="3.5" /><circle cx="81" cy="25" r="3.5" /><circle cx="117" cy="25" r="3.5" /><circle cx="144" cy="25" r="3.5" />
          </g>
        </svg>
      </div>
    {/if}
    <p class="sr-only" role="status">{selected ? `${selected.label} setup: ${steps.length} steps` : 'Choose a connector type to reveal its setup steps.'}</p>
    <h3 id={`${id}-choose`}>Choose a connector type</h3>
    <div class="tiles" role="group" aria-labelledby={`${id}-choose`}>
      {#each choices as choice (choice.kind)}
        {@const unavailable = choice.kind === 'native' && !nativeAvailable}
        <Button variant="secondary" class="connector-type-tile" disabled={unavailable || picker.handingOff} aria-pressed={picker.kind === choice.kind} onclick={() => picker.select(choice.kind)}>
          <span class="icon" aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
              {#if choice.icon === 'catalog'}<path d="M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h6v6h-6z" />
              {:else if choice.icon === 'document'}<path d="M6 3h8l4 4v14H6z M14 3v5h4 M9 12h6 M9 16h6" />
              {:else if choice.icon === 'portable'}<path d="M3 8l9-5 9 5v8l-9 5-9-5z M3 8l9 5 9-5 M12 13v8" />
              {:else}<path d="m10 13 4-4 M9 16l-2 2a3.5 3.5 0 0 1-5-5l4-4a3.5 3.5 0 0 1 5 0 M13 8l2-2a3.5 3.5 0 0 1 5 5l-4 4a3.5 3.5 0 0 1-5 0" />{/if}
            </svg>
          </span>
          <strong>{choice.label}</strong>
          <span class="description">{#if unavailable}{nativeUnavailable ? 'The native connector catalog could not be loaded.' : 'No native connectors are currently available to add.'}{:else}{choice.description}{/if}</span>
        </Button>
      {/each}
    </div>
    <footer><Button disabled={!selected || (selected.kind === 'native' && !nativeAvailable)} aria-disabled={picker.handingOff || undefined} onclick={next}>Next</Button></footer>
    {/if}
  </ModalShell>
{/if}

<style>
  h3 { margin: 0 0 .75rem; font-size: 1.0625rem; letter-spacing: -.02em; }
  .initial-progress { position: relative; }
  .branch-preview { position: absolute; inset: -.15rem auto auto 4rem; width: min(10rem, 60%); height: 1.875rem; color: var(--admin-muted); pointer-events: none; }
  .tiles { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .625rem; }
  .tiles :global(.connector-type-tile) { display: grid; align-content: start; justify-items: start; gap: .5rem; height: auto; min-width: 0; padding: .75rem; border-radius: 16px; border: 1px solid var(--admin-border-strong); text-align: start; white-space: normal; line-height: 1.4; background: var(--admin-soft); }
  .tiles :global(.connector-type-tile:not(:disabled):hover), .tiles :global(.connector-type-tile[aria-pressed='true']) { background: var(--admin-accent-soft); border-color: var(--admin-accent); }
  .description { color: var(--admin-muted); font-size: .75rem; font-weight: 400; }
  .icon { display: grid; place-items: center; width: 2.1rem; aspect-ratio: 1; border: 1px solid var(--admin-accent-border); border-radius: 30%; background: var(--admin-panel); color: var(--admin-accent); }
  footer { display: flex; justify-content: flex-end; margin-top: 1rem; padding-top: .875rem; border-top: 1px solid var(--admin-border); }
  .submitted { display: grid; gap: .5rem; list-style: none; padding: 0; }
  .submitted :global(button) { align-items: flex-start; display: flex; gap: .75rem; height: auto; padding: .75rem; text-align: start; white-space: normal; width: 100%; }
  .submitted-copy { display: grid; gap: .25rem; }
  .choose-actions { justify-content: flex-start; }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
  @media (max-width: 32rem) {
    .tiles { grid-template-columns: 1fr; }
    .tiles :global(.connector-type-tile) { grid-template-columns: 2.1rem minmax(0, 1fr); gap: .2rem .6rem; }
    .icon { grid-row: span 2; }
  }
</style>
