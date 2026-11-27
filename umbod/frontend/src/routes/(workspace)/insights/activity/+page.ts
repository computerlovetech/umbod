import { redirect } from '@sveltejs/kit';
import { workspacePresentation } from '#lib/workspace/navigation.js';
import type { PageLoad } from './$types';

export const load = (({ url }: { url: URL }): never => {
  redirect(307, `${workspacePresentation.homeHref}${url.search}${new URL(url.href).hash}`);
}) satisfies PageLoad;
