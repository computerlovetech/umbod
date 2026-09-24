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
    backdrop-filter: blur(16px);
    background: rgb(17 24 39 / 86%);
    border-bottom: 1px solid rgb(255 255 255 / 10%);
    box-sizing: border-box;
    display: flex;
    gap: 1rem;
    justify-content: space-between;
    min-height: 4rem;
    padding: 0.85rem clamp(1rem, 4vw, 2rem);
    position: sticky;
    top: 0;
    z-index: 10;
  }

  .brand {
    color: #f8fafc;
    font-size: 0.95rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-decoration: none;
    text-transform: uppercase;
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
    color: #f8fafc;
    font-size: 0.95rem;
    font-weight: 700;
    max-width: min(16rem, 42vw);
  }

  .account-email {
    color: #cbd5e1;
    font-size: 0.8rem;
    max-width: min(18rem, 48vw);
  }

  @media (width < 36rem) {
    .app-header {
      align-items: flex-start;
      flex-direction: column;
    }

    .account {
      align-items: center;
      text-align: left;
      width: 100%;
    }

    .account-name,
    .account-email {
      max-width: 100%;
    }
  }
</style>
