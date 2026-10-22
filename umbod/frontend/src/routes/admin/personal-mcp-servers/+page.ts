import type { PageLoad } from './$types';

export const load: PageLoad = ({ url }) => ({ requestedId: url.searchParams.get('connector') });
