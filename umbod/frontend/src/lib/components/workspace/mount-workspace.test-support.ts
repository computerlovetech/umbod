import { mount, type Component } from 'svelte';
import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
import type { WorkspaceApi } from '$lib/workspace/api';
import WorkspacePageHarness from './WorkspacePageHarness.test-support.svelte';

export function mountWorkspace<Props extends Record<string, unknown>>(
  Page: Component<Props>,
  options: {
    target: Document | Element | ShadowRoot;
    props: Props & {
      accountIdentity?: HeaderAccountIdentityState;
      createWorkspaceApi: () => WorkspaceApi;
    };
  },
  pathname: string
): ReturnType<typeof mount> {
  return mount(WorkspacePageHarness<Props>, {
    target: options.target,
    props: { Page, pageProps: options.props, inputs: options.props, pathname }
  });
}
