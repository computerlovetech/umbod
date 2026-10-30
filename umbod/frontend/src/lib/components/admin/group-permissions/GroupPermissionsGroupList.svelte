<script lang="ts" generics="Group extends { label: string; description: string }">
  let { groups, groupId, selectedGroupId, onselect }: {
    groups: readonly Group[];
    groupId: (group: Group) => string;
    selectedGroupId: string | null;
    onselect: (id: string) => void;
  } = $props();

  const initials = (label: string): string => label.trim().split(/\s+/).slice(0, 2).map((word) => word.slice(0, 1)).join('').toUpperCase() || '?';
</script>

<ul class="groups">
  {#each groups as group (groupId(group))}
    <li>
      <button
        class={['group-button', { selected: selectedGroupId === groupId(group) }]}
        type="button"
        aria-current={selectedGroupId === groupId(group) ? 'true' : undefined}
        onclick={() => onselect(groupId(group))}
      >
        <span class="avatar" aria-hidden="true">{initials(group.label)}</span>
        <span class="group-name">{group.label}{#if group.description}<small>{group.description}</small>{/if}</span>
      </button>
    </li>
  {/each}
</ul>

<style>
  .groups { list-style: none; margin: 0; padding: 0; }
  .group-button { align-items: center; background: transparent; border: 0; border-top: 1px solid var(--admin-border); border-radius: 0; color: var(--admin-ink); cursor: pointer; display: flex; font: inherit; font-size: 13px; font-weight: 600; gap: 11px; padding: 11px 15px; text-align: left; width: 100%; }
  .group-button:hover { background: var(--admin-hover); }
  .group-button.selected { background: var(--admin-accent-soft); box-shadow: inset 3px 0 0 var(--admin-accent); }
  .group-button:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: -3px; }
  .avatar { align-items: center; background: var(--admin-ink); border-radius: 50%; color: var(--admin-on-action); display: inline-flex; flex-shrink: 0; font-size: 11px; font-weight: 700; height: 26px; justify-content: center; width: 26px; }
  .group-name { display: block; flex: 1; min-width: 0; overflow-wrap: anywhere; }
  small { color: var(--admin-muted); display: block; font-size: 11px; font-weight: 400; line-height: 1.5; }
</style>
