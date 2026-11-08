<script lang="ts">
  import type { ComponentProps } from 'svelte';
  import ModalShell from './ModalShell.svelte';

  let { current, submit }: { current: () => Omit<ComponentProps<typeof ModalShell>, 'children'>; submit: () => void } = $props();
</script>

<ModalShell {...current()}>
  <p id="modal-description">Modal details</p>
  <form onsubmit={(event) => { event.preventDefault(); submit(); }}>
    <input aria-label="Name" />
    <button type="button" data-dialog-cancel>Cancel</button>
    <button type="submit">Save</button>
  </form>
</ModalShell>
