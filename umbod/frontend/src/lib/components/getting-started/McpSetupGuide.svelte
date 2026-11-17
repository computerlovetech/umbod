<script lang="ts">
  import CopyableValue from '#lib/components/admin/connectors/CopyableValue.svelte';
  import SegmentedRadio from '#lib/components/shared/SegmentedRadio.svelte';
  import '#lib/styles/subpage-navigation.css';
  import { PluginInstallationState, installationPlatforms, installationHarnesses } from './plugin-installation-state.svelte';

  let {
    installerBaseUrl
  }: {
    installerBaseUrl: string;
  } = $props();
  const installation = new PluginInstallationState(() => installerBaseUrl);
  const identifier = $props.id();

  function movePlatform(event: KeyboardEvent): void {
    if (!installation.movePlatform(event.key)) return;
    event.preventDefault();
    const button = event.currentTarget;
    if (!(button instanceof HTMLButtonElement)) return;
    button.closest('[role="tablist"]')?.querySelector<HTMLButtonElement>(`[data-platform="${installation.platform}"]`)?.focus();
  }
</script>

<section aria-label="Harness setup guides" class="installation">
  <div class="subpage-navigation platform-tabs" role="tablist" aria-label="Operating system">
    {#each installationPlatforms as platform (platform.id)}
      <button
        type="button"
        role="tab"
        class="subpage-navigation-item"
        id={`${identifier}-${platform.id}`}
        aria-selected={installation.platform === platform.id}
        aria-controls={`${identifier}-installation`}
        tabindex={installation.platform === platform.id ? 0 : -1}
        data-platform={platform.id}
        onclick={() => installation.selectPlatform(platform.id)}
        onkeydown={movePlatform}
      >{platform.label}</button>
    {/each}
  </div>

  <div role="tabpanel" id={`${identifier}-installation`} aria-labelledby={`${identifier}-${installation.platform}`} tabindex="0">
    <div class="install-card">
      <SegmentedRadio label="Coding harness" options={installationHarnesses} value={installation.harness} onchange={installation.selectHarness} />
      <div class="command-heading">
        <h2>Install Umbod</h2>
        <span>{installation.shell}</span>
      </div>
      <CopyableValue value={installation.command} />
      <p class="requirement">Requires {installation.harnessLabel}{installation.platform === 'windows' ? ' and PowerShell 5.1+' : ', Python 3.8+ and curl'}. No administrator access required.</p>
      <div class="install-links">
        <a href={installation.scriptUrl} target="_blank" rel="noreferrer">Inspect installer</a>
        <a href={installation.documentationUrl} target="_blank" rel="noreferrer">{installation.harnessLabel} documentation</a>
      </div>
    </div>
  </div>
</section>

<style>
  .installation { max-width: 960px; }
  .platform-tabs { margin-bottom: 24px; }
  .install-card { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel); display: grid; gap: 20px; min-width: 0; padding: 24px; }
  .command-heading { align-items: center; display: flex; flex-wrap: wrap; gap: 8px 16px; justify-content: space-between; }
  h2 { color: var(--admin-ink); font-size: 18px; margin: 0; }
  .command-heading span { color: var(--admin-muted); font-size: 13px; }
  p { color: var(--admin-muted); font-size: 14px; line-height: 1.6; margin: 8px 0 0; }
  .requirement { margin: 0; }
  .install-links { display: flex; flex-wrap: wrap; gap: 12px 24px; }
  a { color: var(--admin-accent-strong); font-size: 13px; text-underline-offset: 3px; }
  [role='tabpanel']:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: 4px; }
  @media (max-width: 480px) { .install-card { padding: 18px; } }
</style>
