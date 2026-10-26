<script lang="ts">
  import { onMount } from 'svelte';
  import { adminApi } from '$lib/admin/infrastructure/admin-api';
  import FilesystemAccessEditor from './FilesystemAccessEditor.svelte';
  import { FilesystemAccessState } from './filesystem-access-state.svelte';
  const api = adminApi();
  const state = new FilesystemAccessState(api.filesystem, api.groups);
  onMount(() => { void state.load(); return state.dispose; });
</script>

<FilesystemAccessEditor {state} />
