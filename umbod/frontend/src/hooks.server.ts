import type { CurrentUserIdentity } from '$lib/header/accountIdentity';
import { currentUserIdentitySchema } from '$lib/header/accountIdentity';
import { forwardedAuthHeaders, privateApiBaseUrl } from '$lib/admin/infrastructure/transport';
import { emitStructuredLog, requestTraceContext } from '$lib/server/logging';
import type { Handle, RequestEvent } from '@sveltejs/kit';

const oauthSignInPath = '/oauth2/sign_in';

export const handle: Handle = async ({ event, resolve }) => {
  const startedAt = performance.now();
  const { traceId, spanId } = requestTraceContext(event.request);
  try {
    const response = await handleRequest(event, resolve);
    emitRequestLog({ event, status: response.status, startedAt, traceId, spanId });
    return response;
  } catch (error) {
    emitRequestLog({ event, status: 500, startedAt, traceId, spanId, error });
    throw error;
  }
};

async function handleRequest(event: RequestEvent, resolve: Parameters<Handle>[0]['resolve']): Promise<Response> {
  if (isAdminPath(event.url.pathname)) {
    const authenticationResponse = await loadCurrentUser(event);
    if (authenticationResponse.status === 401) {
      return signInResponse(event.url);
    }
    event.locals.currentUser = authenticationResponse.currentUser;
  } else {
    event.locals.currentUser = null;
  }

  const response = await resolve(event);
  if (!event.url.pathname.startsWith('/_app/immutable/')) {
    response.headers.set('cache-control', 'no-store');
  }
  return response;
}

type RequestLogContext = {
  event: RequestEvent;
  status: number;
  startedAt: number;
  traceId: string;
  spanId: string;
  error?: unknown;
};

function emitRequestLog({ event, status, startedAt, traceId, spanId, error }: RequestLogContext): void {
  emitStructuredLog({
    body: 'http server request completed',
    severity: status >= 500 ? 'error' : 'info',
    traceId,
    spanId,
    error,
    attributes: {
      'http.request.method': event.request.method,
      'http.response.status_code': status,
      'url.path': event.url.pathname,
      'server.address': event.url.hostname,
      ...(event.url.port ? { 'server.port': Number(event.url.port) } : {}),
      'http.server.request.duration_ms': Math.max(0, performance.now() - startedAt)
    }
  });
}

type AuthenticationResponse =
  | { status: 401; currentUser: null }
  | { status: 'resolved'; currentUser: CurrentUserIdentity | null };

async function loadCurrentUser(event: RequestEvent): Promise<AuthenticationResponse> {
  let response: Response;
  try {
    response = await event.fetch(`${privateApiBaseUrl()}/admin/users`, {
      headers: forwardedAuthHeaders(event.request)
    });
  } catch {
    return { status: 'resolved', currentUser: null };
  }
  if (response.status === 401) {
    return { status: 401, currentUser: null };
  }
  if (!response.ok) {
    return { status: 'resolved', currentUser: null };
  }
  return { status: 'resolved', currentUser: currentUserIdentitySchema.parse(await response.json()) };
}

function signInResponse(url: URL): Response {
  const returnPath = `${url.pathname}${url.search}`;
  const location = `${oauthSignInPath}?rd=${encodeURIComponent(returnPath)}`;
  return new Response(null, { status: 303, headers: { location, 'cache-control': 'no-store' } });
}

function isAdminPath(pathname: string): boolean {
  return pathname === '/admin' || pathname.startsWith('/admin/');
}
