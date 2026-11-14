import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ url }) => {
  redirect(307, `/admin/insights/agent-behaviour${url.search}${url.hash}`);
};
