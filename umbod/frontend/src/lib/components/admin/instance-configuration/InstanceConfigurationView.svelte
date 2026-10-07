<script lang="ts">
  import { BrowserClipboardWriter } from '$lib/admin/clipboard';
  import type { InstanceConfigurationPageData } from '$lib/admin/instance-configuration';
  import { useToast } from '$lib/components/feedback';
  import { InstanceConfigurationCopyState } from './instance-configuration-copy-state.svelte';
  import { InstanceSettingsState } from './instance-settings-state.svelte';
  import SettingRow from './SettingRow.svelte';

  let { state }: { state: InstanceConfigurationPageData } = $props();
  const copyState = new InstanceConfigurationCopyState(new BrowserClipboardWriter(), useToast());
  const settings = new InstanceSettingsState(() => state);
  const sections = [
    { id: 'addresses', label: 'Addresses and browser access', description: 'Find the public addresses and allowed browser origins for this instance.', href: '/admin/mcp-setup', link: 'MCP setup guide' },
    { id: 'access', label: 'Access and sign-in', description: 'Review who can sign in and use administration. Group permissions control tool access, not membership of the administrator group.', href: '/admin/group-permissions', link: 'Manage group permissions' },
    { id: 'tools', label: 'Tool behavior and limits', description: 'Review how tools are offered and the limits applied to their use.', href: '/admin/connectors', link: 'Manage connectors' }
  ] as const;
</script>

<header class="page-header">
  <p class="admin-eyebrow">Administration</p>
  <h1 class="admin-title">Instance settings</h1>
  <p class="admin-lede">Review how your Umbod instance is configured. These settings are managed by your deployment team and cannot be changed here.</p>
  <span class="read-only">Read-only · Deployment managed</span>
  <p class="supporting">These are configured values, not health or connectivity checks.</p>
</header>

{#if state.status === 'failed'}
  <section class="state-card" aria-live="polite">
    <p>{state.message}</p>
    <a class="admin-button" href="/admin/instance-configuration">{state.retryLabel}</a>
  </section>
{:else if state.status === 'empty'}
  <section class="state-card"><p>No non-secret instance configuration entries are available</p></section>
{:else}
  <div class="settings">
    <section class="panel essentials" aria-labelledby="essentials-title">
      <h2 id="essentials-title">Essentials</h2>
      <dl>
        {#each settings.presentation.essentials as item (item.variable)}
          <div><dt>{item.label}</dt><dd>{item.value}</dd></div>
        {/each}
      </dl>
    </section>
    {#each sections as section (section.id)}
      <section class="panel" aria-labelledby={`section-${section.id}`}>
        <h2 id={`section-${section.id}`}>{section.label}</h2>
        <p class="supporting">{section.description} <a href={section.href}>{section.link}</a></p>
        <dl>
          {#each settings.presentation[section.id] as setting (setting.entry.variable)}
            <SettingRow {setting} {copyState} />
          {/each}
        </dl>
        {#if settings.presentation[section.id].length === 0}<p class="supporting">No settings available in this section.</p>{/if}
      </section>
    {/each}
    <details class="panel advanced">
      <summary>Advanced deployment details</summary>
      <p class="supporting">Deployment-level settings, grouped by their original configuration context.</p>
      {#each settings.presentation.advanced as group (group.id)}
        <section aria-labelledby={`advanced-${group.id}`}>
          <h3 id={`advanced-${group.id}`}>{group.label}</h3>
          <dl>
            {#each group.entries as setting (setting.entry.variable)}
              <SettingRow {setting} {copyState} />
            {/each}
          </dl>
        </section>
      {/each}
    </details>
  </div>
{/if}

<style>
  .page-header { margin-bottom: 24px; }
  .read-only { display: inline-block; background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 6px 10px; font-size: 13px; }
  .supporting { color: var(--admin-muted); font-size: 14px; line-height: 1.6; }
  .settings { display: grid; gap: 20px; min-width: 0; }
  .panel, .state-card { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel); padding: 20px 24px; min-width: 0; overflow-wrap: anywhere; }
  h2 { font-size: 19px; margin: 0 0 12px; }
  h3 { font-size: 16px; margin: 20px 0 12px; }
  dl { margin: 0; }
  .essentials dl { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 18px; }
  .essentials dt { color: var(--admin-muted); font-size: 13px; margin-bottom: 4px; }
  .essentials dd { margin: 0; font-weight: 600; }
  summary { cursor: pointer; font-size: 18px; font-weight: 600; }
  a { color: var(--admin-accent); }
  a:focus-visible, summary:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: 3px; }
  @media (max-width: 640px) { .panel, .state-card { padding: 18px 16px; } }
</style>
