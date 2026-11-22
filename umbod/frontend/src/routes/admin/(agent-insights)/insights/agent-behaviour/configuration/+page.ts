import { redirect } from '@sveltejs/kit';
import { agentDiagnosticsHref } from '#lib/workspace/navigation.js';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ url }) => {
  redirect(307, `${agentDiagnosticsHref}${url.search}${new URL(url.href).hash}`);
};
