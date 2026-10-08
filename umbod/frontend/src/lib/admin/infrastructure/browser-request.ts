import { HttpError, NetworkError } from './transport';

export class BrowserRequestError extends Error {
  constructor(readonly status: number | undefined, readonly cause?: unknown) {
    super(status === undefined ? 'The service could not be reached' : `Request failed with status ${status}`);
    this.name = 'BrowserRequestError';
  }
}

export async function browserRequest<T>(operation: () => Promise<T>): Promise<T> {
  try { return await operation(); } catch (cause) {
    if (cause instanceof HttpError) throw new BrowserRequestError(cause.status, cause);
    if (cause instanceof NetworkError) throw new BrowserRequestError(undefined, cause);
    throw cause;
  }
}
