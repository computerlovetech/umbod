import { redirect } from '@sveltejs/kit';
import { personalInsightsHref } from '#lib/workspace/navigation.js';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ url }) => {
  redirect(307, `${personalInsightsHref}${url.search}${new URL(url.href).hash}`);
};
