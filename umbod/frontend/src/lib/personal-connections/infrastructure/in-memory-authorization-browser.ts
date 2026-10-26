import type { AuthorizationBrowser, AuthorizationWindow } from '../authorization-browser';
import { authorizationUrlSchema } from '../domain/schemas';

export class InMemoryAuthorizationWindow implements AuthorizationWindow {
  closed = false;
  url = 'about:blank';

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

  reserve = (): AuthorizationWindow => {
    const reserved = new InMemoryAuthorizationWindow();
    this.windows.push(reserved);
    return reserved;
  };
}
