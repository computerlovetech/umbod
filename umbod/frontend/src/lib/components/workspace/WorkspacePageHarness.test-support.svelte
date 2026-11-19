<script lang="ts" generics="Props extends Record<string, unknown>">
  import type { Component } from 'svelte';
  import type { HeaderAccountIdentityState } from '#lib/header/accountIdentity.js';
  import type { WorkspaceApi } from '#lib/workspace/api.js';
  import ToastProvider from '#lib/components/feedback/ToastProvider.svelte';
  import WorkspaceFrame from './WorkspaceFrame.svelte';

  let { Page, pageProps, inputs, pathname }: {
    Page: Component<Props>;
    pageProps: Props;
    inputs: { accountIdentity?: HeaderAccountIdentityState; createWorkspaceApi: () => WorkspaceApi };
    pathname: string;
  } = $props();
</script>

<ToastProvider>
  <WorkspaceFrame {pathname} accountIdentity={inputs.accountIdentity ?? { kind: 'hidden' }} createWorkspaceApi={inputs.createWorkspaceApi}>
    <Page {...pageProps} />
  </WorkspaceFrame>
</ToastProvider>
