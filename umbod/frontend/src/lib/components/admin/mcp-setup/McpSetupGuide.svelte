<script lang="ts">
  import CopyableValue from '$lib/components/admin/connectors/CopyableValue.svelte';

  type Props = { mcpEndpoint: string };
  let { mcpEndpoint }: Props = $props();

  const copilotConfiguration = $derived(`{
  "servers": {
    "umbod": {
      "type": "http",
      "url": "${mcpEndpoint}"
    }
  }
}`);
</script>

<header>
  <p class="admin-eyebrow">Agent harness setup</p>
  <h1 class="admin-title">Connect Umbod</h1>
  <p class="admin-lede">Give your AI tools access to the connectors and capabilities published by this Umbod instance.</p>
</header>

<section class="connection-card" aria-labelledby="connection-title">
  <div>
    <p class="step-label">Your custom MCP endpoint</p>
    <h2 id="connection-title">Copy once, connect anywhere</h2>
  </div>
  <CopyableValue value={mcpEndpoint} />
  <ol>
    <li>Copy the endpoint above.</li>
    <li>Add it as a custom remote MCP server in your harness.</li>
    <li>Complete authentication, review the available tools, and start a new conversation.</li>
  </ol>
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
    <pre><code>{copilotConfiguration}</code></pre>
    <ol start="3">
      <li>Run <strong>MCP: List Servers</strong>, start Umbod, and authenticate if prompted.</li>
      <li>Open Copilot Chat in Agent mode and enable the Umbod tools.</li>
    </ol>
  </article>
</div>

<style>
  header { margin-bottom: 28px; }
  h2 { color: var(--admin-ink); font-size: 17px; line-height: 1.35; margin: 0; }
  .connection-card, .guide-card { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: 12px; box-shadow: 0 1px 2px rgb(15 15 15 / 3%); }
  .connection-card { display: grid; gap: 18px; padding: 22px; }
  .connection-card :global(.copyable-value) { background: var(--admin-soft); max-width: 640px; width: 100%; }
  .step-label { color: var(--admin-accent-strong); font-size: 12px; font-weight: 700; letter-spacing: .06em; margin: 0 0 5px; text-transform: uppercase; }
  .guides { display: grid; gap: 14px; grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: 18px; }
  .guide-card { min-width: 0; padding: 20px; }
  .guide-heading { align-items: center; display: flex; gap: 12px; margin-bottom: 18px; }
  .guide-heading p { color: var(--admin-muted); font-size: 13px; margin: 2px 0 0; }
  .icon { align-items: center; background: #f3f3f1; border: 1px solid var(--admin-border); border-radius: 9px; display: inline-flex; flex: 0 0 38px; height: 38px; justify-content: center; }
  .icon img { height: 20px; width: 20px; }
  .icon.anthropic { background: #f1e6d5; }
  .icon.copilot { background: #efe7ff; }
  ol { color: var(--admin-ink); font-size: 14px; line-height: 1.55; margin: 0; padding-left: 22px; }
  li + li { margin-top: 8px; }
  p { color: var(--admin-muted); font-size: 14px; line-height: 1.5; }
  strong { color: var(--admin-ink); }
  code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  li code { background: var(--admin-accent-soft); border-radius: 4px; color: var(--admin-ink); padding: 2px 4px; }
  pre { background: var(--admin-navy); border-radius: 8px; color: #f8fafc; font-size: 12px; line-height: 1.55; margin: 14px 0; overflow-x: auto; padding: 14px; white-space: pre-wrap; word-break: break-word; }
  .note { border-top: 1px solid var(--admin-border); font-size: 12px; margin: 18px 0 0; padding-top: 13px; }
  @media (max-width: 900px) { .guides { grid-template-columns: 1fr; } }
</style>
