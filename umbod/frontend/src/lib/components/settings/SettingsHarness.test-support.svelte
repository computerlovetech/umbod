<script lang="ts">
  import { untrack } from 'svelte';
  import ProfilePage from '../../../routes/(workspace)/settings/+page.svelte';
  import type { WorkspaceScope } from '#lib/workspace/workspace-scope.svelte.js';
  import { provideWorkspace } from '#lib/workspace/workspace-context.js';

  let { workspace }: { workspace: WorkspaceScope } = $props();
  provideWorkspace(untrack((): WorkspaceScope => workspace));
</script>

<ProfilePage />
