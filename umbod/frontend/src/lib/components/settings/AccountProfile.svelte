<script lang="ts">
  import AccountPicture from '#lib/components/header/AccountPicture.svelte';
  import type { HeaderAccountIdentityState } from '#lib/header/accountIdentity.js';

  let { identity }: { identity: HeaderAccountIdentityState } = $props();
</script>

<section aria-labelledby="profile-title">
  <header class="section-heading">
    <h2 id="profile-title">Profile</h2>
    <p>Your identity in Umbod.</p>
  </header>
  {#if identity.kind === 'visible'}
    <div class="admin-panel profile-card">
      <header class="identity">
        <AccountPicture picture={identity.picture} label="Current account picture" --account-picture-size="3.125rem" />
        <div>
          <h3>{identity.name}</h3>
          <p>Signed-in account</p>
        </div>
      </header>
      <dl>
        <div>
          <dt>Display name</dt>
          <dd>{identity.name}</dd>
        </div>
        {#if identity.email !== null}
          <div>
            <dt>Email address</dt>
            <dd>{identity.email}</dd>
          </div>
        {/if}
      </dl>
    </div>
  {:else}
    <p class="admin-message">Account details are unavailable.</p>
  {/if}
</section>

<style>
  .section-heading {
    margin-bottom: 1.25rem;
  }

  h2, h3, p, dl, dd {
    margin: 0;
  }

  h2 {
    font-size: clamp(1.5rem, 3cqi, 1.85rem);
    letter-spacing: -.04em;
    line-height: 1.2;
    margin-bottom: .375rem;
  }

  h3 {
    font-size: 1rem;
  }

  p {
    color: var(--admin-muted);
  }

  .profile-card {
    margin: 0;
    padding: 0;
    overflow-wrap: anywhere;
  }

  .identity, dl > div {
    display: flex;
    align-items: center;
    gap: .875rem;
    padding: 1rem clamp(.875rem, 3cqi, 1.25rem);
  }

  .identity p {
    font-size: .875rem;
  }

  dl > div {
    justify-content: space-between;
    align-items: baseline;
    border-top: 1px solid var(--admin-border);
  }

  dt {
    flex: 0 0 auto;
    font-weight: 600;
  }

  dd {
    text-align: right;
  }

  @container (max-width: 24rem) {
    dl > div {
      flex-direction: column;
      gap: .25rem;
    }

    dd {
      text-align: left;
    }
  }
</style>
