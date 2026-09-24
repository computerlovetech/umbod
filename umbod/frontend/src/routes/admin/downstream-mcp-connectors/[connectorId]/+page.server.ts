import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = ({ params }) => {
  redirect(308, `/admin/downstream-mcp-connectors?connector=${encodeURIComponent(params.connectorId)}`);
};
