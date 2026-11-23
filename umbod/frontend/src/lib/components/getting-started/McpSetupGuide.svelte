<script lang="ts">
  import { onDestroy, tick } from 'svelte';
  import CopyableValue from '#lib/components/admin/connectors/CopyableValue.svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import { InstallationWizardState } from './installation-wizard-state.svelte';
  import { installationPlatforms, installationHarnesses } from './plugin-installation-state.svelte';
  import { BrowserNavigatorClipboardWriter } from '#lib/admin/clipboard.js';
  import type { TelemetryInstallClaims } from '#lib/telemetry-setup/api.js';

  let { installerBaseUrl, installClaims }: {
    installerBaseUrl: string;
    installClaims?: TelemetryInstallClaims;
  } = $props();

  const wizard = new InstallationWizardState(() => installerBaseUrl, () => installClaims, new BrowserNavigatorClipboardWriter());
  const installation = wizard.installation;
  const identifier = $props.id();
  const headingId = `${identifier}-step-title`;

  onDestroy(() => wizard.clearClaim());

  async function navigate(transition: () => void): Promise<void> {
    transition();
    await tick();
    document.getElementById(headingId)?.focus();
  }
</script>

<section aria-label="Harness setup guides" class="wizard">
  <nav class="rail" aria-label="Installer steps">
    {#each wizard.steps as step, index (step.id)}
      <button type="button" aria-current={wizard.step.id === step.id ? 'step' : undefined}
        onclick={() => navigate(() => wizard.goTo(step.id))}>
        <span class="number" aria-hidden="true">{index + 1}</span>
        <span>{step.label}{#if wizard.summary[step.id]}<small>{wizard.summary[step.id]}</small>{/if}</span>
      </button>
    {/each}
  </nav>

  <div class="step-body">
    <p class="step-count">Step {wizard.stepNumber} of {wizard.steps.length}</p>
    <h2 id={headingId} tabindex="-1">{wizard.step.heading}</h2>

    {#if wizard.step.id === 'platform'}
      <fieldset class="choices" style:--columns={3}>
        <legend class="visually-hidden">Platform</legend>
        {#each installationPlatforms as platform (platform.id)}
          {@render choice('platform', platform.id, platform.label, platform.shell, installation.platform === platform.id, () => wizard.selectPlatform(platform.id), platform.icon)}
        {/each}
      </fieldset>
    {:else if wizard.step.id === 'harness'}
      <fieldset class="choices">
        <legend class="visually-hidden">Harness</legend>
        {#each installationHarnesses as harness (harness.value)}
          {@render choice('harness', harness.value, harness.label, undefined, installation.harness === harness.value, () => wizard.selectHarness(harness.value), harness.icon)}
        {/each}
      </fieldset>
    {:else if wizard.step.id === 'telemetry'}
      <fieldset class="choices">
        <legend class="visually-hidden">Telemetry</legend>
        {@render choice('telemetry', 'skip', 'Without telemetry', 'Leave telemetry settings unchanged.', !wizard.includesLogs, () => wizard.selectTelemetry('skip'))}
        {@render choice('telemetry', 'logs', 'With telemetry', installation.harness === 'codex' ? 'Review and optionally save Umbod as the default logs destination in Codex.' : 'Configure Claude Code to send logs to Umbod after restart.', wizard.includesLogs, () => wizard.selectTelemetry('logs'))}
      </fieldset>
    {:else}
      <dl class="summary">
        {#each wizard.steps as step (step.id)}
          {#if wizard.summary[step.id]}
            <div><dt>{step.label}</dt><dd>{wizard.summary[step.id]}</dd></div>
          {/if}
        {/each}
      </dl>
      <div class="install-card">
        <div class="command-heading"><h3>Install command</h3><span>{wizard.includesLogs && installation.platform === 'macos' ? 'Terminal · Bash or zsh' : installation.shell}</span></div>
        {#if wizard.includesLogs}
          {@const claim = wizard.claim}
          <p>{installation.harness === 'codex' ? "The setup code is single-use and expires after 10 minutes. Run the command on a trusted machine. If you save the Codex settings, don't sync or share the configuration file containing the token." : 'The setup code is single-use and expires after 10 minutes. Run the command on a trusted machine.'}</p>
          {#if claim.status === 'ready'}
            <p role="status">{claim.copy === 'copied' ? 'Copied. ' : claim.copy === 'failed' ? 'Could not copy automatically. ' : ''}Run this single-use command promptly on a trusted machine. Keep it private.</p>
            {#if claim.copy === 'failed'}<code class="claim-command">{claim.command}</code>{/if}
            <div class="install-links">
              <Button variant="secondary" disabled={claim.copy === 'pending'} onclick={() => wizard.copyPreparedCommand()}>Copy install command</Button>
              <Button variant="secondary" disabled={claim.copy === 'pending'} onclick={() => wizard.prepareAndCopy()}>Generate new command</Button>
            </div>
          {:else}
            {#if claim.status === 'pending'}
              <p role="status">Preparing your install command…</p>
            {:else if claim.status === 'error'}
              <p class="error" role="alert">Could not prepare your install command.</p>
            {:else if claim.status === 'expired'}
              <p role="status">Your install command has expired.</p>
            {/if}
            <Button disabled={claim.status === 'pending'} onclick={() => wizard.prepareAndCopy()}>
              {claim.status === 'expired' ? 'Generate new command' : 'Copy install command'}
            </Button>
          {/if}
        {:else}
          <CopyableValue value={installation.command} />
        {/if}
        <p class="requirement">{installation.requirements}{wizard.includesLogs && installation.harness === 'codex' && installation.platform !== 'windows' ? ' Saving Codex telemetry requires Python 3.11 or later.' : ''}</p>
        <div class="install-links">
          <a href={installation.scriptUrl} target="_blank" rel="noreferrer">Inspect installer</a>
          <a href={installation.documentationUrl} target="_blank" rel="noreferrer">{installation.harnessLabel} documentation</a>
        </div>
      </div>
    {/if}

    <div class="actions">
      {#if wizard.step.id !== 'platform'}
        <Button variant="secondary" onclick={() => navigate(() => wizard.back())}>Back</Button>
      {/if}
      {#if wizard.step.id !== 'review'}
        <Button class="continue" onclick={() => navigate(() => wizard.continue())}>Continue</Button>
      {/if}
    </div>
  </div>
</section>

{#snippet choice(group: string, value: string, label: string, hint: string | undefined, checked: boolean, select: () => void, icon?: string)}
  <label class="choice">
    {#if icon}
      <img src={icon} alt="" width="24" height="24" />
    {:else if group === 'telemetry'}
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        {#if value === 'logs'}<path d="M6 3h8l4 4v14H6zm8 0v5h4m-9 4h6m-6 4h6" />
        {:else}<circle cx="12" cy="12" r="8" /><path d="m6.3 6.3 11.4 11.4" />{/if}
      </svg>
    {/if}
    <span><strong>{label}</strong>{#if hint}<small>{hint}</small>{/if}</span>
    <input type="radio" name={`${identifier}-${group}`} {value} {checked} onchange={select} />
  </label>
{/snippet}

<style>
  .wizard { max-width: 960px; display: grid; grid-template-columns: 210px minmax(0, 1fr); border: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel); }
  .rail { background: var(--admin-sidebar); padding: 20px 12px; border-right: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel) 0 0 var(--admin-radius-panel); }
  .rail button { border: 0; border-radius: var(--admin-radius); background: transparent; color: var(--admin-ink); cursor: pointer; display: flex; align-items: center; gap: 8px; text-align: left; width: 100%; padding: 10px; margin-bottom: 4px; font: inherit; font-size: 14px; font-weight: 600; }
  .rail button:hover, .choice:hover { background: var(--admin-hover); }
  .rail button[aria-current='step'], .choice:has(:checked) { background: var(--admin-accent-soft); color: var(--admin-accent-strong); }
  .number { display: inline-grid; place-items: center; width: 26px; height: 26px; flex: none; border: 1px solid var(--admin-border); border-radius: 50%; background: var(--admin-panel); font-size: 12px; }
  [aria-current='step'] .number { background: var(--admin-accent); border-color: var(--admin-accent); color: var(--admin-on-action); }
  small { display: block; font-weight: 400; color: var(--admin-muted); }
  .step-body { min-width: 0; padding: 24px; }
  .step-count { color: var(--admin-accent-strong); font-weight: 650; font-size: 12px; margin-bottom: 5px; }
  h2, h3, p { margin: 0; }
  h2 { font-size: 22px; }
  h3 { font-size: 18px; }
  p { color: var(--admin-muted); font-size: 14px; line-height: 1.6; }
  .choices, .summary { display: grid; grid-template-columns: repeat(var(--columns, 2), minmax(0, 1fr)); gap: 10px; margin: 16px 0 0; padding: 0; border: 0; min-inline-size: 0; }
  .choice { display: flex; align-items: flex-start; gap: 10px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 12px; cursor: pointer; }
  .choice:has(:checked) { border-color: var(--admin-accent); }
  .choice input { flex: none; margin: 4px 0 0 auto; accent-color: var(--admin-accent); }
  .choice img, .choice svg { flex: none; width: 24px; height: 24px; object-fit: contain; }
  .choice svg { fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
  .claim-command { max-width: 100%; overflow-wrap: anywhere; background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 0.6rem 0.7rem; font-family: var(--admin-mono); font-size: 0.8rem; user-select: all; }
  .choice:has(:focus-visible), h2:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: 3px; }
  .summary { --columns: 3; }
  .summary div { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 9px 12px; }
  .summary dt { font-size: 12px; color: var(--admin-muted); }
  .summary dd { margin: 0; font-weight: 650; }
  .install-card { display: grid; justify-items: start; gap: 12px; min-width: 0; margin-top: 20px; }
  .command-heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; width: 100%; }
  .command-heading span { color: var(--admin-muted); font-size: 13px; }
  .error { color: var(--admin-danger-text); }
  .install-links { display: flex; flex-wrap: wrap; gap: 12px 24px; }
  a { color: var(--admin-accent-strong); font-size: 13px; text-underline-offset: 3px; }
  .actions { display: flex; gap: 10px; margin-top: 20px; }
  .actions :global(.continue) { margin-inline-start: auto; }
  .visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
  @media (max-width: 850px) { .choices { grid-template-columns: 1fr; } }
  @media (max-width: 650px) {
    .wizard { grid-template-columns: minmax(0, 1fr); }
    .rail { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); padding: 8px; border-right: 0; border-bottom: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel) var(--admin-radius-panel) 0 0; }
    .rail button { flex-direction: column; gap: 4px; font-size: 12px; text-align: center; padding: 6px 2px; margin: 0; }
    .rail small { display: none; }
    .step-body { padding: 16px; }
    .summary { grid-template-columns: 1fr; }
  }
</style>
