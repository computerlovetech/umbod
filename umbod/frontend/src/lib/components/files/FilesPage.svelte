<script lang="ts">
  import { useWorkspace } from '#lib/workspace/workspace-context.js';
  import { WorkspaceIdentityBinding } from '#lib/workspace/workspace-scope.svelte.js';
  import { afterNavigate, goto } from '$app/navigation';
  import { onMount, onDestroy } from 'svelte';
  import { navigateToSignIn } from '#lib/admin/infrastructure/transport.js';
  import type { FilesApi } from '#lib/files/api.js';
  import { browserFilesApi } from '#lib/files/infrastructure/files-api.js';
  import { FilesState, filesHref } from '#lib/files/state/files-state.svelte.js';
  import { UploadState } from '#lib/files/state/upload-state.svelte.js';
  import { NewFolderState } from '#lib/files/state/new-folder-state.svelte.js';
  import FilesContent from './FilesContent.svelte';
  import { publicConfigurationProvider } from '#lib/admin/infrastructure/public-configuration.js';
  import type { PreviewConfigurationProvider } from '#lib/files/preview/configuration.js';
  import { browserTransport } from '#lib/admin/infrastructure/transport.js';
  import { FileContentRoute } from '#lib/files/infrastructure/file-content-route.js';
  import type { FileContentPort } from '#lib/files/preview/ports.js';
  import { PreviewRegistry } from '#lib/files/preview/ports.js';
  import { FilePreviewState } from '#lib/files/preview/file-preview-state.svelte.js';
  import { markdownPreviewAdapter } from './preview/markdown-adapter';
  import { pdfPreviewAdapter } from './preview/pdf-adapter';
  import { imagePreviewAdapter } from './preview/image-adapter';
  import { textPreviewAdapter } from './preview/text-adapter';
  import { csvPreviewAdapter } from './preview/csv-adapter';

  let {
    createApi = browserFilesApi,
    configuration = publicConfigurationProvider,
    createContentSource = (configuration: PreviewConfigurationProvider): FileContentPort => new FileContentRoute(browserTransport(), configuration),
    signIn = navigateToSignIn
  }: {
    createApi?: () => FilesApi;
    configuration?: PreviewConfigurationProvider;
    createContentSource?: (configuration: PreviewConfigurationProvider) => FileContentPort;
    signIn?: () => void;
  } = $props();

  function createFilesApi(): FilesApi {
    return createApi();
  }

  function createPreview(): FilePreviewState {
    return new FilePreviewState(createContentSource(configuration), new PreviewRegistry([markdownPreviewAdapter, pdfPreviewAdapter, imagePreviewAdapter, csvPreviewAdapter, textPreviewAdapter]), configuration);
  }

  const api = createFilesApi();
  const preview = createPreview();
  const state = new FilesState(api, async (id: string): Promise<void> => { await goto(filesHref(id)); }, preview);
  const folder = new NewFolderState(api, state);
  const upload = new UploadState(api, state);
  const workspace = useWorkspace();
  const identity = new WorkspaceIdentityBinding(workspace.access, (identity, changed): void => {
    if (changed) { folder.navigate(); upload.navigate(); }
    state.observeAccountIdentity(identity, changed);
  });

  function dispose(): void {
    state.dispose();
    folder.dispose();
    upload.dispose();
  }

  onDestroy(workspace.registerDisposal(dispose));
  $effect.pre(identity.observe);

  afterNavigate(({ to, shallow }) => {
    if (shallow) return;
    if (to?.url.pathname !== '/files') { preview.reset(); state.deletion.reset(); state.rowDeletion.reset(); state.sharing.reset(); return; }
    const target = to.url.searchParams.get('node');
    if (state.isCurrentTarget(target)) return;
    folder.navigate();
    upload.navigate();
    void state.load(target);
  });

  onMount(() => dispose);
</script>

<svelte:head><title>Files · Umbod</title></svelte:head>
<FilesContent {state} {folder} {upload} {signIn} />
