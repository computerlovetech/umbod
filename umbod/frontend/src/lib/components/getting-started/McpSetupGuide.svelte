<script lang="ts">
  import CopyableValue from '$lib/components/admin/connectors/CopyableValue.svelte';
  import { McpSetupState } from './mcp-setup-state.svelte';

  let { mcpEndpoint }: { mcpEndpoint: string } = $props();
  const state = new McpSetupState(() => mcpEndpoint);
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
      <p>Run in your terminal to add Umbod to your user configuration:</p>
      <CopyableValue value={state.codexCommand} />
      <ol>
        <li>Run <code>codex mcp login umbod</code> and complete browser sign-in if authentication is required.</li>
        <li>Run <code>codex mcp list</code> to confirm the server is configured.</li>
        <li>Start Codex and use <code>/mcp</code> to inspect the available server and tools.</li>
      </ol>
      <a href="https://developers.openai.com/codex/mcp/" target="_blank" rel="noreferrer">Codex MCP documentation</a>
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

  <details class="other-clients">
    <summary>Other MCP clients</summary>
    <div class="guides">
      <article class="guide-card">
        <h3>ChatGPT</h3>
        <ol>
          <li>Open <strong>Plugins</strong> in ChatGPT and select <strong>+ → Add custom MCP server</strong>.</li>
          <li>Name it Umbod and enter the MCP endpoint above under <strong>Connection</strong>.</li>
          <li>Configure the authentication method supplied by your Umbod operator, review the warning, then select <strong>Create as a plugin</strong>.</li>
          <li>Review the discovered tools, install the plugin, and type <code>@</code> in a new conversation to select it.</li>
        </ol>
        <p>Developer mode is not required for the Plugins flow. Availability depends on your account and workspace policy. ChatGPT must be able to reach the endpoint.</p>
        <a href="https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt" target="_blank" rel="noreferrer">ChatGPT custom MCP documentation</a>
      </article>

      <article class="guide-card">
        <h3>Claude and Cowork</h3>
        <ol>
          <li>Open <strong>Customize → Connectors</strong> in Claude.</li>
          <li>Select <strong>+ Add → Add custom connector</strong>, name it Umbod, and enter the MCP endpoint above.</li>
          <li>Select <strong>Continue</strong>, review authentication, then choose <strong>Sign in now</strong> and <strong>Add</strong> to finish connecting.</li>
          <li>Enable the connector for your conversation or Cowork task.</li>
        </ol>
        <p>Availability depends on your plan. Team and Enterprise workspaces may require administrator provisioning. Claude and Cowork remote connectors must be able to reach Umbod from Anthropic's infrastructure, not just your laptop.</p>
        <a href="https://support.claude.com/en/articles/11175166-getting-started-with-custom-connectors-using-remote-mcp" target="_blank" rel="noreferrer">Claude custom connector documentation</a>
      </article>

      <article class="guide-card">
        <h3>GitHub Copilot in VS Code</h3>
        <ol>
          <li>Run <strong>MCP: Add Server</strong> from the Command Palette and choose <strong>HTTP</strong>.</li>
          <li>Enter the MCP endpoint above, use server ID <code>umbod</code>, and choose <strong>Global → Copilot Global</strong> for personal configuration.</li>
          <li>Review trust prompts and complete browser sign-in if authentication is required.</li>
          <li>Run <strong>MCP: List Servers</strong> to inspect Umbod, then enable its tools in an agent chat.</li>
        </ol>
        <p>Alternatively, merge this into <code>~/.copilot/mcp-config.json</code>, keeping existing servers:</p>
        <pre><code>{state.copilotConfiguration}</code></pre>
        <a href="https://code.visualstudio.com/docs/agent-customization/mcp-servers" target="_blank" rel="noreferrer">VS Code MCP documentation</a>
      </article>
    </div>
  </details>
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
  pre { background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); color: var(--admin-ink); font-size: 12px; line-height: 1.6; overflow-x: auto; padding: 14px; white-space: pre-wrap; overflow-wrap: anywhere; }
  .other-clients { margin-top: 20px; }
  summary { color: var(--admin-ink); cursor: pointer; font-size: 14px; font-weight: 600; }
  summary:focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 4px; }
  @media (max-width: 900px) { .guides { grid-template-columns: 1fr; } }
  @media (max-width: 480px) { .connection-card, .guide-card { padding: 18px; } }
</style>
