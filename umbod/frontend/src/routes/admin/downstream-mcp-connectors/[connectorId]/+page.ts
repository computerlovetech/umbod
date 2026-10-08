import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ params }) => {
  redirect(308, `/admin/downstream-mcp-connectors?connector=${encodeURIComponent(params.connectorId)}`);
};
