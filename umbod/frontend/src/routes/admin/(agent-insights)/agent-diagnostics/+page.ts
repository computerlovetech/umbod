import { redirect } from '@sveltejs/kit';
import { legacyAgentDiagnosticsTarget } from '#lib/workspace/navigation.js';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ url }): void => {
  if (url.searchParams.get('tab') === 'reporting') redirect(307, legacyAgentDiagnosticsTarget(url));
};
