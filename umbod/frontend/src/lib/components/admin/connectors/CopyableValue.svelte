<script lang="ts">
  import { BrowserNavigatorClipboardWriter, type ClipboardWriter } from '$lib/admin/clipboard';
  import { useToast } from '$lib/components/feedback';
  import { CopyableValueState } from './copyable-value-state.svelte';

  type Props = {
    value: string;
    clipboard?: ClipboardWriter;
  };

  let { value, clipboard = new BrowserNavigatorClipboardWriter() }: Props = $props();
  const toast = useToast();
  const state = $derived(new CopyableValueState(value, clipboard, toast));
</script>

<div class:failed={state.feedback === 'failed'} class="copyable-value">
  <code title={value}>{value}</code>
  <button type="button" onclick={state.copy} aria-label={`Copy ${value}`} title="Copy URI">
    {#if state.feedback === 'copied'}
      <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m4.5 10.5 3.2 3.2 7.8-8" /></svg>
    {:else}
      <svg viewBox="0 0 20 20" aria-hidden="true"><rect x="6.5" y="5.5" width="9" height="11" rx="1.5" /><path d="M13.5 5.5v-1A1.5 1.5 0 0 0 12 3H5A1.5 1.5 0 0 0 3.5 4.5v9A1.5 1.5 0 0 0 5 15.5h1.5" /></svg>
    {/if}
  </button>
</div>

<style>
  .copyable-value { align-items: stretch; background: #f1f3f6; border: 1px solid #dfe2e7; border-radius: 8px; display: flex; max-width: 100%; overflow: hidden; transition: border-color 120ms ease, box-shadow 120ms ease; }
  .copyable-value:focus-within { border-color: #9abcf8; box-shadow: 0 0 0 3px #e8f0fe; }
  .copyable-value.failed { border-color: #d8a29d; }
  code { align-items: center; background: transparent; display: flex; flex: 1 1 auto; font-size: 0.8rem; min-height: 2.25rem; min-width: 0; overflow: hidden; padding: 0.45rem 0.7rem; text-overflow: ellipsis; white-space: nowrap; }
  button { align-items: center; background: #e2e6ee; border: 0; border-left: 1px solid #d5d9e1; color: #4d5665; cursor: pointer; display: inline-flex; flex: 0 0 2.65rem; justify-content: center; padding: 0; transition: background 120ms ease, color 120ms ease; }
  button:hover { background: #d7dce6; color: #262d38; }
  button:focus-visible { outline: 2px solid #2859c5; outline-offset: -3px; }
  svg { fill: none; height: 1.1rem; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; width: 1.1rem; }
</style>
