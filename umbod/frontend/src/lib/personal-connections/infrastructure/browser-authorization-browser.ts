import type { AuthorizationBrowser, AuthorizationWindow } from '../authorization-browser';
import { authorizationUrlSchema } from '../domain/schemas';
import { renderAuthorizationLoadingScreen } from './authorization-loading-screen';

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
    reserve: (displayName: string): AuthorizationWindow | null => {
      let popup: Window | null = null;
      try {
        if (window.matchMedia('(max-width: 640px), (hover: none) and (pointer: coarse)').matches) {
          popup = window.open('about:blank', '_blank');
        } else {
          const width = Math.min(520, window.screen.availWidth);
          const height = Math.min(680, window.screen.availHeight);
          const left = Math.round(window.screenX + Math.max(0, (window.outerWidth - width) / 2));
          const top = Math.round(window.screenY + Math.max(0, (window.outerHeight - height) / 2));
          popup = window.open('about:blank', '_blank', `popup=yes,width=${width},height=${height},left=${left},top=${top}`);
        }
        if (!popup) return null;
        popup.opener = null;
        renderAuthorizationLoadingScreen(popup, displayName);
        return new BrowserAuthorizationWindow(popup);
      } catch {
        if (popup) new BrowserAuthorizationWindow(popup).close();
        return null;
      }
    }
  };
}
