import type { Component } from 'svelte';
import { render } from 'svelte/server';
import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
import type { WorkspaceApi } from '$lib/workspace/api';
import WorkspacePageHarness from './WorkspacePageHarness.test-support.svelte';

export function renderWorkspace<Props extends Record<string, unknown>>(
  Page: Component<Props>,
  options: {
    props: Props & {
      accountIdentity?: HeaderAccountIdentityState;
      createWorkspaceApi?: () => WorkspaceApi;
    };
  },
  pathname: string
): ReturnType<typeof render> {
  return render(WorkspacePageHarness<Props>, {
    props: {
      Page, pageProps: options.props, pathname,
      inputs: { ...options.props, createWorkspaceApi: options.props.createWorkspaceApi ?? (() => ({ profile: { get: async (): Promise<never> => { throw new Error('Unexpected server profile read'); } } })) }
    }
  });
}
