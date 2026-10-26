<script lang="ts">
  import { onMount } from 'svelte';
  import { adminApi } from '$lib/admin/infrastructure/admin-api';
  import FilesystemAccessEditor from './FilesystemAccessEditor.svelte';
  import { FilesystemAccessState } from './filesystem-access-state.svelte';
  const state = new FilesystemAccessState(adminApi().filesystem);
  onMount(() => { void state.load(); return state.dispose; });
</script>

<FilesystemAccessEditor {state} />
