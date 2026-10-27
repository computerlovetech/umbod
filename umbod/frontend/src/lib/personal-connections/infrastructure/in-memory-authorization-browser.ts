import type { AuthorizationBrowser, AuthorizationWindow } from '../authorization-browser';
import { authorizationUrlSchema } from '../domain/schemas';

export class InMemoryAuthorizationWindow implements AuthorizationWindow {
  closed = false;
  url = 'about:blank';

  constructor(readonly displayName: string) {}

  navigate = (url: string): boolean => {
    if (this.closed || !authorizationUrlSchema.safeParse(url).success) return false;
    this.url = url;
    return true;
  };

  close = (): void => {
    this.closed = true;
  };
}

export class InMemoryAuthorizationBrowser implements AuthorizationBrowser {
  readonly windows: InMemoryAuthorizationWindow[] = [];

  reserve = (displayName: string): AuthorizationWindow => {
    const reserved = new InMemoryAuthorizationWindow(displayName);
    this.windows.push(reserved);
    return reserved;
  };
}
