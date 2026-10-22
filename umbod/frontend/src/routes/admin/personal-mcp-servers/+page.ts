import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ url }) => {
  const query = new URLSearchParams(url.searchParams);
  const selected = query.get('connector');
  if (selected !== null && !/^[a-zA-Z0-9_-]{1,128}$/.test(selected)) query.delete('connector');
  redirect(307, `/admin/downstream-mcp-connectors${query.size ? `?${query}` : ''}`);
};
