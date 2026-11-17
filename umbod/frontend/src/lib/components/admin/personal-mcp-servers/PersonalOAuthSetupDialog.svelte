<script lang="ts">
  import ModalShell from '#lib/components/shared/ModalShell.svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import LoadingButton from '#lib/components/admin/shared/LoadingButton.svelte';
  import type { PersonalOAuthSetupState } from './personal-oauth-setup-state.svelte';

  let { state, close, edit, published = false, publish }: {
    state: PersonalOAuthSetupState;
    close: () => void;
    edit: (trigger: HTMLElement) => void;
    published?: boolean;
    publish?: () => void;
  } = $props();

  const titles: Record<PersonalOAuthSetupState['outcome'], string> = {
    loading: 'Loading configuration',
    checking: 'Checking configuration',
    ready: 'Configuration ready',
    changes_required: 'Changes required',
    failed: 'Check failed',
    required: 'Check required',
    unknown: 'Check result unavailable',
    denied: 'Admin access required'
  };
</script>

<ModalShell title="Configuration check" titleId="personal-oauth-setup-title" {close} closeDisabled={Boolean(state.pending)} --modal-width="30rem" --modal-overflow="auto">
  <div class="setup">
    <section class={['result', `result--${state.outcome}`]} role={state.outcome === 'changes_required' || state.outcome === 'failed' || state.outcome === 'denied' ? 'alert' : 'status'}>
      <h3>{state.outcome === 'ready' && !published ? 'Ready to publish' : titles[state.outcome]}</h3>
      {#if state.outcome === 'required'}
        <p>Check the saved configuration before publishing.</p>
      {:else if state.outcome !== 'ready' && state.message}
        <p>{state.message}</p>
      {:else if state.outcome === 'changes_required'}
        <p>Review the server settings, then check again.</p>
      {:else if state.outcome === 'unknown'}
        <p>A check is still running. Refresh its status before starting another.</p>
      {/if}
    </section>
    {#if state.outcome === 'changes_required' && state.returnedScopes !== null}
      <dl>
        <div><dt>Requested permissions</dt><dd><code>{state.policy?.requested_scopes.join(' ') || 'None'}</code></dd></div>
        <div><dt>Provider returned</dt><dd><code>{state.returnedScopes.join(' ') || 'None'}</code></dd></div>
      </dl>
    {/if}
    {#if state.outcome === 'changes_required' && state.discovery && state.policy && (state.policy.client.kind === 'preconfigured_public' || state.policy.client.kind === 'preconfigured_confidential') && state.policy.client.issuer_url !== state.discovery.issuer_url}
      <div class="correction"><span>Required authorization provider</span><code>{state.discovery.issuer_url}</code></div>
    {/if}
    {#if state.outcome === 'ready'}
      <p>Only provider metadata was checked.</p>
      {#if state.policy?.client.kind === 'dynamic_public' || state.policy?.client.kind === 'dynamic_confidential'}
        <p>Automatic application registration and each user’s sign-in happen when they connect; this check does not prove either will succeed.</p>
      {/if}
    {/if}
    {#if state.outcome === 'ready' && (state.policy?.client.kind === 'preconfigured_public' || state.policy?.client.kind === 'preconfigured_confidential') && state.discovery}
      <div class="correction"><p>Client credentials are not tested. Confirm them and this callback URL in your provider.</p><code>{state.discovery.redirect_uri}</code></div>
    {/if}
    <footer>
      {#if state.outcome === 'ready'}
        {#if publish && !published}
          <Button variant="secondary" data-dialog-cancel onclick={close}>Close</Button>
          <Button onclick={publish}>Publish</Button>
        {:else}
          <Button data-dialog-cancel onclick={close}>Done</Button>
        {/if}
      {:else}
        <Button variant="secondary" data-dialog-cancel disabled={Boolean(state.pending)} onclick={close}>Close</Button>
        {#if !state.accessDenied}
          {#if state.requiresRefresh}
            <LoadingButton label="Refresh status" loadingLabel="Refreshing status" loading={state.pending === 'loading'} disabled={Boolean(state.pending)} onclick={state.refresh} />
          {:else if state.outcome === 'changes_required'}
            <Button variant="secondary" disabled={!state.canCheck} onclick={state.check}>Check again</Button>
            <Button disabled={state.locked} onclick={(event) => edit(event.currentTarget)}>Edit settings</Button>
          {:else}
            <LoadingButton label={state.outcome === 'failed' ? 'Check again' : 'Check configuration'} loadingLabel="Checking configuration" loading={state.pending === 'validation' || state.pending === 'discovery'} disabled={!state.canCheck} onclick={state.check} />
          {/if}
        {/if}
      {/if}
    </footer>
  </div>
</ModalShell>

<style>
  .setup { display: grid; gap: 1rem; min-width: 0; padding-top: 1rem; }
  .result { background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); display: grid; gap: .5rem; padding: 1rem; }
  .result--ready { background: var(--admin-success-bg); border-color: var(--admin-success-border); color: var(--admin-success-text); }
  .result--changes_required, .result--unknown { background: var(--admin-warning-bg); border-color: var(--admin-warning-border); color: var(--admin-warning-text); }
  .result--failed, .result--denied { background: var(--admin-danger-bg); border-color: var(--admin-danger-border); color: var(--admin-danger-text); }
  h3 { font-size: 1.125rem; margin: 0; }
  p { margin: 0; line-height: 1.5; }
  dl { display: grid; gap: .75rem; margin: 0; }
  dt, .correction { color: var(--admin-muted); font-size: .875rem; }
  dd { margin: .25rem 0 0; }
  code { overflow-wrap: anywhere; }
  .correction { display: grid; gap: .5rem; }
  footer { border-top: 1px solid var(--admin-border); display: flex; flex-wrap: wrap; gap: .75rem; justify-content: flex-end; padding-top: 1rem; }
</style>
