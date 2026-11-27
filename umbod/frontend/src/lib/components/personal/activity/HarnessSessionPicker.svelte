<script lang="ts">
  import Button from '#lib/components/admin/shared/Button.svelte';
  import DateTimeView from '#lib/components/shared/DateTimeView.svelte';
  import { harnessClientLabel, sessionIdentity } from '#lib/insights/activity/presentation.js';
  import type { ActivitySessionSummary, ActivitySessionKey } from '#lib/insights/activity/domain/activity-schemas.js';

  let { sessions, selected, onselect }: {
    sessions: readonly ActivitySessionSummary[];
    selected: string;
    onselect: (key: ActivitySessionKey) => void;
  } = $props();

  function navigate(event: KeyboardEvent): void {
    if (!(event.currentTarget instanceof HTMLButtonElement)) return;
    const list = event.currentTarget.closest('ul');
    if (!list) return;
    const buttons = Array.from(list.querySelectorAll('button'));
    const index = buttons.indexOf(event.currentTarget);
    const target = { ArrowLeft: index - 1, ArrowRight: index + 1, Home: 0, End: buttons.length - 1 }[event.key];
    if (target === undefined || !buttons[target]) return;
    event.preventDefault();
    buttons[target].focus();
  }
</script>

<ul aria-label="Harness sessions, newest first">
  {#each sessions as session (sessionIdentity(session.key))}
    <li>
      <Button variant="secondary" aria-pressed={selected === sessionIdentity(session.key)} onclick={() => onselect(session.key)} onkeydown={navigate}>
        <span class="card">
          <strong>{harnessClientLabel(session.key.source)}</strong>
          <code title={session.key.session_id}>{session.key.session_id}</code>
          <span>Last observed <DateTimeView value={session.last_seen_at} /></span>
        </span>
      </Button>
    </li>
  {/each}
</ul>

<style>
  ul { display: flex; gap: 0.75rem; list-style: none; margin: 0; padding: 0.375rem; overflow-x: auto; scroll-snap-type: x proximity; }
  li { flex: 0 0 min(16rem, 92%); min-width: 0; scroll-snap-align: start; }
  li :global(button) { width: 100%; height: 100%; text-align: left; }
  li :global(button[aria-pressed='true']) { border-color: var(--admin-accent); background: var(--admin-soft); }
  .card { display: grid; width: 100%; min-width: 0; gap: 0.375rem; }
  code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .card > span { font-size: 0.75rem; color: var(--admin-muted); }
</style>
