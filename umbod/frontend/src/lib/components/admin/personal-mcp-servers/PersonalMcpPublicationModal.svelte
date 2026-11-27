<script lang="ts">
  import Disclosure from '#lib/components/shared/Disclosure.svelte';
  import ModalShell from '#lib/components/shared/ModalShell.svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';

  let { name, onconfirm, oncancel }: {
    name: string;
    onconfirm: () => void;
    oncancel: () => void;
  } = $props();
</script>

<ModalShell
  title="Publish connector?"
  titleId="personal-mcp-publication-title"
  descriptionId="personal-mcp-publication-notice"
  close={oncancel}
  --modal-width="28rem"
  --modal-overflow="auto"
>
  <div class="connector">
    <span class="connector-icon">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3v5m8-5v5M6 8h12v3a6 6 0 0 1-12 0V8Zm6 9v4" /></svg>
    </span>
    <div class="identity"><strong>{name}</strong><small>Personal MCP connector</small></div>
  </div>
  <div class="notice" id="personal-mcp-publication-notice">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m10.3 4.2-7.6 13.3a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4m0 3.5h.01" /></svg>
    <div><strong>This changes who can use it</strong><p>Permitted groups can use all its tools, including future tools after discovery.</p></div>
  </div>
  <div class="access-details">
    <Disclosure --disclosure-trigger-width="fit-content" --disclosure-trigger-padding="0.25rem 0">
      {#snippet label()}Access &amp; setup details{/snippet}
      <p>This does not make the connector available to everyone. Account authorization, owner enablement, and tool discovery remain separate steps.</p>
    </Disclosure>
  </div>
  <footer>
    <Button variant="secondary" data-dialog-cancel onclick={oncancel}>Cancel</Button>
    <Button onclick={onconfirm}>Publish connector</Button>
  </footer>
</ModalShell>

<style>
  .connector { align-items: center; display: flex; gap: 0.75rem; margin: 1.25rem 0; }
  .connector-icon { align-items: center; background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: 10px; color: var(--admin-accent); display: flex; flex: none; height: 2.5rem; justify-content: center; width: 2.5rem; }
  svg { fill: none; flex: none; height: 1.25rem; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.7; width: 1.25rem; }
  .identity { min-width: 0; overflow-wrap: anywhere; }
  .identity strong { display: block; font-size: 0.875rem; font-weight: 600; }
  small { color: var(--admin-muted); display: block; font-size: 0.75rem; margin-top: 0.25rem; }
  .notice { align-items: flex-start; background: var(--admin-warning-bg); border: 1px solid var(--admin-warning-border); border-radius: 8px; color: var(--admin-warning-text); display: flex; gap: 0.625rem; padding: 0.875rem 0.75rem; }
  .notice svg { margin-top: 0.125rem; }
  .notice strong { display: block; font-size: 0.8125rem; font-weight: 600; margin-bottom: 0.25rem; }
  p { font-size: 0.8125rem; line-height: 1.6; margin: 0; }
  .access-details { color: var(--admin-muted); font-size: 0.8125rem; margin-top: 1.125rem; }
  .access-details p { margin-top: 0.625rem; }
  footer { border-top: 1px solid var(--admin-border); display: flex; flex-wrap: wrap; gap: 0.5rem; justify-content: flex-end; margin-top: 1.5rem; padding-top: 1rem; }
</style>
