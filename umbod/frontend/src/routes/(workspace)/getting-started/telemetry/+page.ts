import { redirect } from '@sveltejs/kit';
import { workspaceTokensHref } from '#lib/workspace/navigation.js';
import type { PageLoad } from './$types';

export const load = (({ url }: { url: URL }): never => {
  redirect(307, `${workspaceTokensHref}${url.search}${new URL(url.href).hash}`);
}) satisfies PageLoad;
