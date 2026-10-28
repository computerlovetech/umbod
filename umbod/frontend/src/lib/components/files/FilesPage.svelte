<script lang="ts">
  import { afterNavigate } from '$app/navigation';
  import { onMount } from 'svelte';
  import { adminApi } from '$lib/admin/infrastructure/admin-api';
  import { navigateToSignIn } from '$lib/admin/infrastructure/transport';
  import type { CurrentUserApi } from '$lib/workspace/admin-access';
  import { WorkspaceAccessState } from '$lib/workspace/workspace-access-state.svelte';
  import { workspaceNavigation, workspacePresentation } from '$lib/workspace/navigation';
  import type { FilesApi } from '$lib/files/api';
  import { browserFilesApi } from '$lib/files/infrastructure/files-api';
  import { FilesState } from '$lib/files/state/files-state.svelte';
  import { UploadState } from '$lib/files/state/upload-state.svelte';
  import { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
  import WorkspaceShell from '$lib/components/shared/workspace/WorkspaceShell.svelte';
  import FilesContent from './FilesContent.svelte';

  let {
    createApi = browserFilesApi,
    createCurrentUserApi = adminApi,
    signIn = navigateToSignIn
  }: {
    createApi?: () => FilesApi;
    createCurrentUserApi?: () => CurrentUserApi;
    signIn?: () => void;
  } = $props();

  function createFilesApi(): FilesApi {
    return createApi();
  }

  function createAccess(): WorkspaceAccessState {
    return new WorkspaceAccessState(createCurrentUserApi());
  }

  const api = createFilesApi();
  const state = new FilesState(api);
  const folder = new NewFolderState(api, state);
  const upload = new UploadState(api, state);
  const access = createAccess();

  afterNavigate(({ to }) => {
    if (to?.url.pathname !== '/files') return;
    folder.navigate();
    upload.navigate();
    void state.load(to.url.searchParams.get('node'));
  });

  onMount(() => {
    void access.load();
    return () => {
      state.dispose();
      folder.dispose();
      upload.dispose();
      access.dispose();
    };
  });
</script>

<svelte:head><title>Files · Umbod</title></svelte:head>
<WorkspaceShell {...workspacePresentation} navigationItems={workspaceNavigation(access.adminAccess === 'allowed')} activeItem="files" accountIdentity={access.accountIdentity}>
  <FilesContent {state} {folder} {upload} {signIn} />
</WorkspaceShell>
