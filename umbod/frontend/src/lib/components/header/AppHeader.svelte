<script lang="ts">
  import AccountPicture from '$lib/components/header/AccountPicture.svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';

  let { accountIdentity }: { accountIdentity: HeaderAccountIdentityState } = $props();
</script>

<header class="app-header" aria-label="Application header">
  <a class="brand" href="/">Umbod</a>

  {#if accountIdentity.kind === 'visible'}
    <section class="account" aria-label="Current account">
      <AccountPicture picture={accountIdentity.picture} label="Current account picture" />
      <span class="account-text">
        <span class="account-name">{accountIdentity.name}</span>
        <span class="account-email">{accountIdentity.email}</span>
      </span>
    </section>
  {/if}
</header>

<style>
  .app-header {
    align-items: center;
    background: var(--admin-panel);
    border-bottom: 1px solid var(--admin-border);
    box-sizing: border-box;
    display: flex;
    gap: 1rem;
    justify-content: space-between;
    min-height: 4.5rem;
    padding: 0.85rem clamp(1rem, 4vw, 2rem);
    position: sticky;
    top: 0;
    z-index: 10;
  }

  .brand {
    align-items: center;
    border-radius: var(--admin-radius);
    color: var(--admin-ink);
    display: inline-flex;
    flex-shrink: 0;
    gap: 8px;
    font-size: 24px;
    font-weight: 650;
    letter-spacing: -0.06em;
    text-decoration: none;
  }

  .brand::before {
    background: url('/umbod-logo.svg') center / contain no-repeat;
    content: '';
    height: 32px;
    width: 32px;
  }

  .brand:hover {
    color: var(--admin-accent);
  }

  .account {
    align-items: center;
    display: flex;
    gap: 0.65rem;
    min-width: 0;
    text-align: right;
  }

  .account-text {
    display: grid;
    gap: 0.15rem;
    min-width: 0;
  }

  .account-name,
  .account-email {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .account-name {
    color: var(--admin-ink);
    font-size: 0.95rem;
    font-weight: 600;
    max-width: min(16rem, 42vw);
  }

  .account-email {
    color: var(--admin-muted);
    font-size: 0.8rem;
    max-width: min(18rem, 48vw);
  }

  @media (width < 36rem) {
    .account {
      --account-picture-size: 1.75rem;
    }

    .account-name,
    .account-email {
      max-width: min(10rem, 38vw);
    }
  }
</style>
