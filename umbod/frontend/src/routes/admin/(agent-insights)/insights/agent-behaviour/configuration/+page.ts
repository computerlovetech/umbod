import { redirect } from '@sveltejs/kit';
import { legacyAgentDiagnosticsTarget } from '#lib/workspace/navigation.js';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ url }) => {
  redirect(307, legacyAgentDiagnosticsTarget(url));
};
