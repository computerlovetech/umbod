<script lang="ts">
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import type { AdminPageData } from './+page';

  type AdminOverviewPageData = AdminPageData & {
    accountIdentity?: HeaderAccountIdentityState;
  };

  let { data }: { data: AdminOverviewPageData } = $props();

  const fallbackAccountIdentity: HeaderAccountIdentityState = { kind: 'hidden' };
</script>

<svelte:head>
  <title>Admin</title>
</svelte:head>

<AdminShell activeItem="overview" accountIdentity={data.accountIdentity ?? fallbackAccountIdentity}>
  <div class="admin-page">
    <p class="admin-eyebrow">Umbod</p>
    <h1 class="admin-title">Admin</h1>
    <p class="admin-lede">Manage Umbod administration areas.</p>

    <nav aria-label="Admin navigation">
      <ul>
        {#each data.navigationItems as item (item.href)}
          <li>
            <a class="admin-card-link" href={item.href}>
              <span>{item.label}</span>
              <span aria-hidden="true">→</span>
            </a>
          </li>
        {/each}
      </ul>
    </nav>
  </div>
</AdminShell>

<style>
  ul {
    display: grid;
    gap: 10px;
    list-style: none;
    margin: 32px 0 0;
    padding: 0;
  }
</style>
