<script lang="ts">
  import { afterNavigate, goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { workspaceApi } from '$lib/workspace/infrastructure/workspace-api';
  import { navigateToSignIn } from '$lib/admin/infrastructure/transport';
  import type { WorkspaceApi } from '$lib/workspace/api';
  import { WorkspaceAccessState } from '$lib/workspace/workspace-access-state.svelte';
  import { workspaceNavigation, workspacePresentation } from '$lib/workspace/navigation';
  import type { FilesApi } from '$lib/files/api';
  import { browserFilesApi } from '$lib/files/infrastructure/files-api';
  import { FilesState, filesHref } from '$lib/files/state/files-state.svelte';
  import { UploadState } from '$lib/files/state/upload-state.svelte';
  import { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
  import WorkspaceShell from '$lib/components/shared/workspace/WorkspaceShell.svelte';
  import FilesContent from './FilesContent.svelte';
  import { browserTransport } from '$lib/admin/infrastructure/transport';
  import { FileContentRoute } from '$lib/files/infrastructure/file-content-route';
  import type { FileContentPort } from '$lib/files/preview/ports';
  import { PreviewRegistry } from '$lib/files/preview/ports';
  import { FilePreviewState } from '$lib/files/preview/file-preview-state.svelte';
  import { markdownPreviewAdapter } from './preview/markdown-adapter';
  import { pdfPreviewAdapter } from './preview/pdf-adapter';

  let {
    createApi = browserFilesApi,
    createWorkspaceApi = workspaceApi,
    createContentSource = (): FileContentPort => new FileContentRoute(browserTransport()),
    signIn = navigateToSignIn
  }: {
    createApi?: () => FilesApi;
    createWorkspaceApi?: () => WorkspaceApi;
    createContentSource?: () => FileContentPort;
    signIn?: () => void;
  } = $props();

  function createFilesApi(): FilesApi {
    return createApi();
  }

  function createAccess(): WorkspaceAccessState {
    return new WorkspaceAccessState(createWorkspaceApi());
  }

  function createPreview(): FilePreviewState {
    return new FilePreviewState(createContentSource(), new PreviewRegistry([markdownPreviewAdapter, pdfPreviewAdapter]));
  }

  const api = createFilesApi();
  const preview = createPreview();
  const state = new FilesState(api, async (id: string): Promise<void> => { await goto(filesHref(id)); }, preview);
  const folder = new NewFolderState(api, state);
  const upload = new UploadState(api, state);
  const access = createAccess();

  afterNavigate(({ to }) => {
    if (to?.url.pathname !== '/files') { preview.reset(); state.deletion.reset(); state.rowDeletion.reset(); state.sharing.reset(); return; }
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
<WorkspaceShell {...workspacePresentation} navigationItems={workspaceNavigation(access.adminAccess === 'allowed')} activeItem="files" accountIdentity={access.accountIdentity} contentWidth="wide">
  <FilesContent {state} {folder} {upload} {signIn} />
</WorkspaceShell>
