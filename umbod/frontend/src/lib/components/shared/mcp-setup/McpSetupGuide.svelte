<script lang="ts">
  import CopyableValue from '$lib/components/admin/connectors/CopyableValue.svelte';
  import { BrowserNavigatorClipboardWriter } from '$lib/admin/clipboard';
  import { useToast } from '$lib/components/feedback';
  import { McpSetupState, setupPrompt } from './mcp-setup-state.svelte';

  type Props = { mcpEndpoint: string; compact?: boolean };
  let { mcpEndpoint, compact = false }: Props = $props();
  const state = new McpSetupState(() => mcpEndpoint, new BrowserNavigatorClipboardWriter(), useToast());
</script>

{#if !compact}
<header>
  <p class="admin-eyebrow">Agent harness setup</p>
  <h1 class="admin-title">Connect Umbod</h1>
  <p class="admin-lede">Give your AI tools access to the connectors and capabilities published by this Umbod instance.</p>
</header>

{/if}

<section class={["connection-card", compact && "compact"]} aria-label="MCP setup">
  {#if compact}
    <h2>MCP setup</h2>
  {:else}
    <div>
      <p class="step-label">Your custom MCP endpoint</p>
      <h2>Copy once, connect anywhere</h2>
    </div>
  {/if}
  <CopyableValue value={mcpEndpoint} />
  {#if !compact}
  <ol>
    <li>Copy the endpoint above.</li>
    <li>Add it as a custom remote MCP server in your harness.</li>
    <li>Complete authentication, review the available tools, and start a new conversation.</li>
  </ol>
  {/if}
</section>

{#snippet clientInstructions()}
  {#if compact}
      <ol>
    <li>Copy the endpoint above.</li>
    <li>Add it as a custom remote MCP server in your harness.</li>
    <li>Complete authentication, review the available tools, and start a new conversation.</li>
  </ol>

  {/if}
<section class="connection-card setup-card" aria-labelledby="setup-title">
  <h2 id="setup-title">Help your agent discover connected apps</h2>
  {#if !compact}<p>After connecting, paste this prompt into your agent. It asks your agent to save Umbod discovery guidance in your user-level instructions across projects.</p>{/if}
  <pre><code>{setupPrompt}</code></pre>
  <button type="button" onclick={state.copySetupPrompt}>{state.copied ? 'Copied' : 'Copy setup prompt'}</button>
  <p class="setup-note">Requires an agent that can read MCP resources and edit local instruction files.</p>
</section>

<div class="guides">
  <article class="guide-card">
    <div class="guide-heading">
      <span class="icon"><img src="/icons/openai.svg" alt="" /></span>
      <div><h2>ChatGPT</h2><p>Custom plugin in developer mode</p></div>
    </div>
    <ol>
      <li>Open <strong>Settings → Security and login</strong> and enable developer mode.</li>
      <li>Go to <strong>ChatGPT Plugins</strong>, select the plus button, and paste the endpoint.</li>
      <li>Name the plugin Umbod, add a short description, and select <strong>Create</strong>.</li>
      <li>Review the discovered tools, then select Umbod from the <strong>More</strong> menu in a new chat.</li>
    </ol>
    <p class="note">Developer mode availability depends on your ChatGPT plan and workspace policy.</p>
  </article>

  <article class="guide-card">
    <div class="guide-heading">
      <span class="icon anthropic"><img src="/icons/anthropic.svg" alt="" /></span>
      <div><h2>Claude Code</h2><p>Remote HTTP server from the terminal</p></div>
    </div>
    <p>Run this outside a Claude Code session:</p>
    <pre><code>claude mcp add --transport http --scope user umbod {mcpEndpoint}</code></pre>
    <ol>
      <li>Run <code>claude mcp list</code> to check the connection.</li>
      <li>Open Claude Code and enter <code>/mcp</code> to authenticate if prompted.</li>
      <li>Confirm Umbod is connected and its tools are available.</li>
    </ol>
  </article>

  <article class="guide-card">
    <div class="guide-heading">
      <span class="icon anthropic"><img src="/icons/anthropic.svg" alt="" /></span>
      <div><h2>Claude Cowork</h2><p>Custom web connector</p></div>
    </div>
    <ol>
      <li>In Claude, open <strong>Customize → Connectors</strong>.</li>
      <li>Select <strong>Add custom connector</strong>, enter Umbod as the name, and paste the endpoint.</li>
      <li>Choose the detected authentication settings and select <strong>Add</strong>.</li>
      <li>Connect your account, then enable Umbod for the Cowork conversation.</li>
    </ol>
    <p class="note">On Team and Enterprise plans, an organization owner must add the connector first.</p>
  </article>

  <article class="guide-card">
    <div class="guide-heading">
      <span class="icon copilot"><img src="/icons/githubcopilot.svg" alt="" /></span>
      <div><h2>GitHub Copilot</h2><p>Custom MCP server in VS Code</p></div>
    </div>
    <ol>
      <li>In VS Code, run <strong>MCP: Open User Configuration</strong> from the Command Palette.</li>
      <li>Add the server configuration below and save the file.</li>
    </ol>
    <pre><code>{state.copilotConfiguration}</code></pre>
    <ol start="3">
      <li>Run <strong>MCP: List Servers</strong>, start Umbod, and authenticate if prompted.</li>
      <li>Open Copilot Chat in Agent mode and enable the Umbod tools.</li>
    </ol>
  </article>
</div>

{/snippet}

{#if compact}
  <details class="client-instructions">
    <summary>Client instructions</summary>
    {@render clientInstructions()}
  </details>
{:else}
  {@render clientInstructions()}
{/if}

<style>
  .compact { align-items: center; grid-template-columns: auto minmax(0, 1fr); gap: 16px; padding: 16px; }
  .client-instructions { margin-top: 12px; }
  summary { border-radius: var(--admin-radius); color: var(--admin-ink); cursor: pointer; font-size: 14px; padding: 8px 0; }
  summary:focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  .client-instructions > ol { margin-top: 12px; }
  @media (max-width: 480px) { .compact { grid-template-columns: minmax(0, 1fr); } }
  header { margin-bottom: 32px; }
  h2 { color: var(--admin-ink); font-size: 18px; font-weight: 600; letter-spacing: -0.025em; line-height: 1.35; margin: 0; }
  .connection-card, .guide-card { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel); }
  .connection-card { display: grid; gap: 18px; min-width: 0; padding: 24px; }
  .setup-card { margin-top: 18px; }
  .setup-card p { color: var(--admin-muted); font-size: 14px; line-height: 1.55; margin: 0; }
  .setup-card pre { margin: 0; }
  .setup-card .setup-note { font-size: 12px; }
  .setup-card button { background: var(--admin-accent-strong); border: 0; border-radius: var(--admin-radius); color: var(--admin-panel); cursor: pointer; font: inherit; justify-self: start; padding: 10px 16px; }
  .setup-card button:focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  .connection-card :global(.copyable-value) { background: var(--admin-soft); box-sizing: border-box; max-width: 640px; width: 100%; }
  .step-label { color: var(--admin-accent-strong); font-family: var(--admin-mono); font-size: 11px; font-weight: 500; letter-spacing: .08em; margin: 0 0 5px; text-transform: uppercase; }
  .guides { display: grid; gap: 16px; grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: 18px; }
  .guide-card { min-width: 0; padding: 20px; }
  .guide-heading { align-items: center; display: flex; gap: 12px; margin-bottom: 18px; }
  .guide-heading p { color: var(--admin-muted); font-size: 13px; margin: 2px 0 0; }
  .icon { align-items: center; background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: 9px; display: inline-flex; flex: 0 0 38px; height: 38px; justify-content: center; }
  .icon img { height: 20px; width: 20px; }
  .icon.anthropic { background: #f1e6d5; }
  .icon.copilot { background: #efe7ff; }
  ol { color: var(--admin-ink); font-size: 14px; line-height: 1.55; margin: 0; padding-left: 22px; }
  li + li { margin-top: 8px; }
  .guide-card p { color: var(--admin-muted); font-size: 14px; line-height: 1.5; }
  strong { color: var(--admin-ink); }
  code { font-family: var(--admin-mono); overflow-wrap: anywhere; }
  li code { background: var(--admin-accent-soft); border-radius: 4px; color: var(--admin-ink); padding: 2px 4px; }
  pre { background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); color: var(--admin-ink); font-size: 12px; line-height: 1.55; margin: 14px 0; overflow-x: auto; padding: 14px; white-space: pre-wrap; word-break: break-word; }
  .note { border-top: 1px solid var(--admin-border); font-size: 12px; margin: 18px 0 0; padding-top: 13px; }
  @media (max-width: 480px) { .connection-card, .guide-card { padding: 18px; } }
  @media (max-width: 900px) { .guides { grid-template-columns: 1fr; } }
</style>
