export class BrowserRequestError extends Error {
  constructor(
    readonly status: number | undefined,
    readonly cause?: unknown
  ) {
    super(status === undefined ? 'The service could not be reached' : `Request failed with status ${status}`);
    this.name = 'BrowserRequestError';
  }
}

export async function fetchResponse(request: typeof globalThis.fetch, input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  try {
    return init === undefined ? await request(input) : await request(input, init);
  } catch (error) {
    throw new BrowserRequestError(undefined, error);
  }
}
