export interface AuthorizationWindow {
  navigate(url: string): boolean;
  close(): void;
}

export interface AuthorizationBrowser {
  reserve(): AuthorizationWindow | null;
}
