import { json, type RequestHandler } from '@sveltejs/kit';

export const GET: RequestHandler = ({ request }) => {
	if (!isInternalHealthRequest(request)) {
		return new Response(null, { status: 404 });
	}

	return json({ status: 'ok' });
};

function isInternalHealthRequest(request: Request): boolean {
	const host = request.headers.get('host');

	if (host === null) {
		return false;
	}

	const hostname = host.split(':')[0]?.toLowerCase() ?? '';

	return hostname === '127.0.0.1' || hostname === 'localhost' || hostname === 'frontend';
}
