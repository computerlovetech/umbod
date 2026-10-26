import type { AuthorizationBrowser, AuthorizationWindow } from '../authorization-browser';
import { authorizationUrlSchema } from '../domain/schemas';

class BrowserAuthorizationWindow implements AuthorizationWindow {
  constructor(private readonly popup: Window) {}

  navigate = (url: string): boolean => {
    if (!authorizationUrlSchema.safeParse(url).success) return false;
    try {
      if (this.popup.closed) return false;
      this.popup.location.replace(url);
      return true;
    } catch {
      return false;
    }
  };

  close = (): void => {
    try {
      this.popup.close();
    } catch {}
  };
}

export function browserAuthorizationBrowser(): AuthorizationBrowser {
  return {
    reserve: (): AuthorizationWindow | null => {
      let popup: Window | null = null;
      try {
        popup = window.open('about:blank', '_blank');
        if (!popup) return null;
        popup.opener = null;
        popup.document.title = 'Opening sign-in';
        popup.document.body.textContent = 'Opening sign-in…';
        return new BrowserAuthorizationWindow(popup);
      } catch {
        if (popup) new BrowserAuthorizationWindow(popup).close();
        return null;
      }
    }
  };
}
