<script lang="ts">
  import Button from '#lib/components/admin/shared/Button.svelte';
  import { BrowserNavigatorClipboardWriter, type ClipboardWriter } from '#lib/admin/clipboard.js';
  import { useToast } from '#lib/components/feedback/index.js';
  import { CopyableValueState } from './copyable-value-state.svelte';

  type Props = {
    value: string;
    clipboard?: ClipboardWriter;
    inlineLabel?: string;
  };

  let { value, inlineLabel, clipboard = new BrowserNavigatorClipboardWriter() }: Props = $props();
  const toast = useToast();
  const state = $derived(new CopyableValueState(value, clipboard, toast));
  let code: HTMLElement;

  function selectValue(expectedValue: string): boolean {
    const selection = code?.ownerDocument.getSelection();
    if (!selection || !code.isConnected || code.textContent !== expectedValue) return false;
    const range = code.ownerDocument.createRange();
    range.selectNodeContents(code);
    selection.removeAllRanges();
    selection.addRange(range);
    return true;
  }

  function copy(): Promise<void> {
    const copiedValue = value;
    return state.copy(inlineLabel ? () => selectValue(copiedValue) : undefined);
  }
</script>

<div class={['copyable-value', { failed: state.feedback === 'failed', inline: inlineLabel !== undefined }]}>
  <code bind:this={code} title={value}>{value}</code>
  <Button variant={inlineLabel ? 'secondary' : 'quiet'} size={inlineLabel ? 'compact' : 'normal'} iconOnly={!inlineLabel} onclick={copy} aria-label={`Copy ${inlineLabel ?? value}`} title={`Copy ${inlineLabel ?? 'value'}`}>
    {#if inlineLabel}
      {state.feedback === 'copied' ? 'Copied' : state.feedback === 'selected' ? 'Selected' : 'Copy'}
    {:else if state.feedback === 'copied'}
      <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m4.5 10.5 3.2 3.2 7.8-8" /></svg>
    {:else}
      <svg viewBox="0 0 20 20" aria-hidden="true"><rect x="6.5" y="5.5" width="9" height="11" rx="1.5" /><path d="M13.5 5.5v-1A1.5 1.5 0 0 0 12 3H5A1.5 1.5 0 0 0 3.5 4.5v9A1.5 1.5 0 0 0 5 15.5h1.5" /></svg>
    {/if}
  </Button>
</div>

<style>
  .copyable-value { align-items: stretch; background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: 8px; display: flex; max-width: 100%; overflow: hidden; transition: border-color 120ms ease, box-shadow 120ms ease; }
  .copyable-value:focus-within { border-color: var(--admin-accent); box-shadow: 0 0 0 3px var(--admin-focus); }
  .copyable-value.failed { border-color: var(--admin-danger-border); }
  code { align-items: center; background: transparent; display: flex; flex: 1 1 auto; font-family: var(--admin-mono); font-size: 0.8rem; min-height: 2.25rem; min-width: 0; overflow-wrap: anywhere; padding: 0.45rem 0.7rem; white-space: normal; }
  .inline { align-items: center; background: transparent; border: 0; border-radius: 0; gap: 0.5rem; overflow: visible; }
  .inline:focus-within { box-shadow: none; }
  .inline code { min-height: 0; padding: 0; }
  .inline :global(button) { flex: none; min-inline-size: 5rem; }
  svg { fill: none; height: 1.1rem; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; width: 1.1rem; }
</style>
