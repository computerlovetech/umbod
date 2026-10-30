<script lang="ts">
  import type { Snippet } from 'svelte';

  let { groupId, label, description, badge }: {
    groupId: string;
    label: string;
    description: string;
    badge?: Snippet;
  } = $props();

  const initials = (value: string): string => value.trim().split(/\s+/).slice(0, 2).map((word) => word.slice(0, 1)).join('').toUpperCase() || '?';
</script>

<header class="group-header">
  <span class="avatar" aria-hidden="true">{initials(label)}</span>
  <div>
    <h2>{label}</h2>
    {#if description}<p>{description}</p>{/if}
    <p>Provider group ID: <code>{groupId}</code></p>
  </div>
  {#if badge}{@render badge()}{/if}
</header>

<style>
  .group-header { align-items: flex-start; display: flex; gap: 12px; margin-bottom: 6px; }
  .group-header > div { flex: 1; min-width: 0; }
  .avatar { align-items: center; background: var(--admin-ink); border-radius: 50%; color: var(--admin-on-action); display: inline-flex; flex-shrink: 0; font-size: 15px; font-weight: 700; height: 38px; justify-content: center; width: 38px; }
  h2 { font-size: 22px; font-weight: 600; letter-spacing: -0.03em; margin: 0; overflow-wrap: anywhere; }
  p { color: var(--admin-muted); font-size: 13px; line-height: 1.55; margin: 0; overflow-wrap: anywhere; }
  @media (max-width: 640px) {
    .group-header { flex-wrap: wrap; }
  }
</style>
