export interface AuthorizationWindow {
  navigate(url: string): boolean;
  close(): void;
}

export interface AuthorizationBrowser {
  reserve(displayName: string): AuthorizationWindow | null;
}
