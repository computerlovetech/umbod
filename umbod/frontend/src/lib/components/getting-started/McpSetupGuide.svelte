<script lang="ts">
  import { onDestroy, untrack } from 'svelte';
  import CopyableValue from '$lib/components/admin/connectors/CopyableValue.svelte';
  import LoadingButton from '$lib/components/admin/shared/LoadingButton.svelte';
  import { BrowserCodexPluginDownloader, BrowserCodexPluginPackager } from '$lib/codex-plugin/browser-package';
  import type { CodexPluginDownloader, CodexPluginPackager } from '$lib/codex-plugin/contracts';
  import { McpSetupState } from './mcp-setup-state.svelte';
  import { CodexPluginState } from './codex-plugin-state.svelte';

  let {
    mcpEndpoint,
    pluginPackager = new BrowserCodexPluginPackager(),
    pluginDownloader = new BrowserCodexPluginDownloader()
  }: {
    mcpEndpoint: string;
    pluginPackager?: CodexPluginPackager;
    pluginDownloader?: CodexPluginDownloader;
  } = $props();
  const state = new McpSetupState(() => mcpEndpoint);
  const plugin = untrack(() => new CodexPluginState(() => mcpEndpoint, pluginPackager, pluginDownloader));
  onDestroy(plugin.dispose);
</script>

<section aria-labelledby="mcp-setup-heading">
  <h2 id="mcp-setup-heading">Connect your harness</h2>
  <p class="intro">Add Umbod as a remote HTTP MCP server to use the connectors and capabilities available to your account.</p>
  <div class="connection-card">
    <h3>MCP endpoint</h3>
    <CopyableValue value={mcpEndpoint} />
    <p>Use your normal account sign-in when prompted. Telemetry tokens do not authenticate MCP connections.</p>
  </div>

  <div class="guides">
    <article class="guide-card">
      <div class="guide-heading"><span class="harness-icon"><img src="/icons/openai.svg" alt="" /></span><h3>Codex</h3></div>
      <p>Download the plugin for this Umbod instance. It bundles the MCP connection and a connected-app discovery skill, without account credentials.</p>
      <LoadingButton type="button" loading={plugin.pending} label="Download Codex plugin" loadingLabel="Preparing ZIP" onclick={plugin.download} />
      {#if plugin.error}
        <p role="alert">{plugin.error}</p>
      {/if}
      {#if plugin.installation}
        <div class="plugin-installation">
          <p role="status">Your browser was asked to save <strong>{plugin.installation.filename}</strong>. Extract the ZIP to a folder you want to keep, then open a terminal in the extracted marketplace folder containing <code>plugins</code> and run:</p>
          <CopyableValue value={plugin.installation.command} />
          <p>In Codex, open <code>/plugins</code> and install Umbod from the added marketplace. Keep the extracted folder in place.</p>
        </div>
      {/if}
      <p>Requires a Codex CLI version with <code>codex plugin</code> support (verified with 0.167.0). The browser downloads the package; it cannot install Codex plugins directly.</p>
      <p>If you already configured an <code>umbod</code> MCP server, inspect it before replacing it. Keep only one Umbod connection enabled; do not remove unrelated configuration.</p>
      <ol>
        <li>After installation, run <code>codex mcp login umbod</code> and complete browser sign-in if authentication is required.</li>
        <li>Start a new Codex session and use <code>/mcp</code> to inspect the connection.</li>
        <li>Ask Codex to verify its Umbod connection and discover available connected apps. Installation alone does not verify app access.</li>
      </ol>
      <details>
        <summary>Manual MCP setup instead</summary>
        <p>This connects MCP without installing the plugin's discovery skill:</p>
        <CopyableValue value={state.codexCommand} />
      </details>
      <a href="https://developers.openai.com/codex/plugins" target="_blank" rel="noreferrer">Codex plugin documentation</a>
    </article>

    <article class="guide-card">
      <div class="guide-heading"><span class="harness-icon anthropic"><img src="/icons/anthropic.svg" alt="" /></span><h3>Claude Code</h3></div>
      <p>Run outside a Claude Code session to configure Umbod across projects:</p>
      <CopyableValue value={state.claudeCommand} />
      <ol>
        <li>Run <code>claude mcp login umbod</code> and complete browser sign-in if authentication is required.</li>
        <li>Start Claude Code and enter <code>/mcp</code> to inspect the connection.</li>
        <li>Confirm the connection and review the available tools before using them.</li>
      </ol>
      <a href="https://code.claude.com/docs/en/mcp" target="_blank" rel="noreferrer">Claude Code MCP documentation</a>
    </article>
  </div>

</section>

<style>
  h2 { color: var(--admin-ink); font-size: 20px; letter-spacing: -0.025em; margin: 0; }
  h3 { color: var(--admin-ink); font-size: 16px; margin: 0; }
  p, ol { color: var(--admin-muted); font-size: 14px; line-height: 1.6; }
  .intro { margin: 8px 0 20px; }
  .connection-card, .guide-card { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel); min-width: 0; padding: 24px; }
  .connection-card { display: grid; gap: 12px; }
  .connection-card p { margin: 0; }
  .guides { display: grid; gap: 16px; grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: 16px; }
  .guide-card :global(.copyable-value) { margin: 16px 0; }
  .guide-heading { align-items: center; display: flex; gap: 12px; margin-bottom: 18px; }
  .harness-icon { align-items: center; background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: 9px; display: inline-flex; flex: 0 0 38px; height: 38px; justify-content: center; }
  .harness-icon img { height: 20px; width: 20px; }
  .harness-icon.anthropic { background: #f1e6d5; }
  ol { color: var(--admin-ink); padding-left: 22px; }
  li + li { margin-top: 10px; }
  a { color: var(--admin-accent-strong); font-size: 13px; text-underline-offset: 3px; }
  code { font-family: var(--admin-mono); overflow-wrap: anywhere; }
  li code { background: var(--admin-accent-soft); border-radius: 4px; padding: 2px 4px; }
  @media (max-width: 900px) { .guides { grid-template-columns: 1fr; } }
  @media (max-width: 480px) { .connection-card, .guide-card { padding: 18px; } }
</style>
