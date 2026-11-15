<script lang="ts" generics="Props extends Record<string, unknown>">
  import type { Component } from 'svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import type { WorkspaceApi } from '$lib/workspace/api';
  import WorkspaceFrame from './WorkspaceFrame.svelte';

  let { Page, pageProps, inputs, pathname }: {
    Page: Component<Props>;
    pageProps: Props;
    inputs: { accountIdentity?: HeaderAccountIdentityState; createWorkspaceApi: () => WorkspaceApi };
    pathname: string;
  } = $props();
</script>

<WorkspaceFrame {pathname} accountIdentity={inputs.accountIdentity ?? { kind: 'hidden' }} createWorkspaceApi={inputs.createWorkspaceApi}>
  <Page {...pageProps} />
</WorkspaceFrame>
