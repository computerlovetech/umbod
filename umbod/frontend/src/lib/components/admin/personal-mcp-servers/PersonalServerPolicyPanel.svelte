<script lang="ts">
  import Button from '#lib/components/admin/shared/Button.svelte';
  import type { ClientKind } from '#lib/admin/personal-mcp-servers/domain/schemas.js';

  let { policy, checkStatus, checkMessage, checked, locked, checkAction, oncheck }: {
    policy: { client: { kind: ClientKind }; requested_scopes: readonly string[] } | null;
    checkStatus: string;
    checkMessage: string;
    checked: boolean;
    locked: boolean;
    checkAction: string;
    oncheck: (trigger: HTMLElement) => void;
  } = $props();

  const clientLabels: Record<ClientKind, string> = {
    dynamic_public: 'Automatic · Public',
    dynamic_confidential: 'Automatic · Confidential',
    preconfigured_public: 'Existing · Public',
    preconfigured_confidential: 'Existing · Confidential'
  };
</script>

<section class="overview" aria-label="Personal authorization">
  <div class="ownership">
    <section class="card" aria-label="Managed by admins">
      <h3><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 8 3v5c0 5-4 8-8 10-4-2-8-5-8-10V6z" /></svg>Managed by admins</h3>
      {#if policy}
        <dl>
          <div><dt>OAuth client</dt><dd>{clientLabels[policy.client.kind]}</dd></div>
          <div><dt>Requested scopes</dt><dd class="scopes">{#each policy.requested_scopes as scope (scope)}<code>{scope}</code>{:else}None requested{/each}</dd></div>
        </dl>
      {/if}
      <div class="check" role="status">
        <div class="check-label" class:checked>
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d={checked ? 'm8 12 3 3 5-6' : 'M12 8v4m0 4h.01'} /></svg>
          {checkStatus}
        </div>
        {#if checkMessage}<p>{checkMessage}</p>{/if}
      </div>
      <div class="actions">
        <Button variant="secondary" disabled={locked} onclick={(event) => oncheck(event.currentTarget)}>{checkAction}</Button>
      </div>
      <p>Group grants cover all tools, including tools found after rediscovery.</p>
    </section>
    <section class="card owner" aria-label="Managed by each user">
      <h3><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="7" r="3.5" /><path d="M5 21v-2a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v2" /></svg>Managed by each user</h3>
      <dl>
        <div><dt>Connection</dt><dd>Enable and sign in</dd></div>
        <div><dt>Tool discovery</dt><dd>Private to each account</dd></div>
      </dl>
      <div class="actions"><a href="/dashboard">Dashboard</a></div>
    </section>
  </div>
</section>

<style>
  .overview { container-type: inline-size; margin-top: 1.25rem; }
  .ownership { display: grid; gap: 0.75rem; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .card { align-content: start; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); display: grid; gap: 0.75rem; min-width: 0; padding: 0.9rem; }
  .owner { background: var(--admin-soft); }
  h3, .check-label { align-items: center; display: flex; gap: 0.5rem; font-size: 0.9rem; font-weight: 650; margin: 0; }
  svg { fill: none; flex: none; height: 1rem; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.7; width: 1rem; }
  dl { display: grid; gap: 0.5rem; margin: 0; }
  dt, p { color: var(--admin-muted); font-size: 0.8rem; margin: 0; }
  dd { font-size: 0.875rem; font-weight: 600; margin: 0; }
  .scopes { display: flex; flex-wrap: wrap; gap: 0.25rem; }
  code { background: var(--admin-soft); border-radius: 0.25rem; min-width: 0; overflow-wrap: anywhere; padding: 0.1rem 0.25rem; }
  .check { border-top: 1px solid var(--admin-border); display: grid; gap: 0.25rem; padding-top: 0.6rem; }
  .checked { color: var(--admin-success-text); }
  .actions { align-items: center; display: flex; flex-wrap: wrap; gap: 0.5rem 0.75rem; }
  a { color: var(--admin-accent); font-size: 0.85rem; font-weight: 600; }
  @container (max-width: 32rem) { .ownership { grid-template-columns: minmax(0, 1fr); } }
</style>
