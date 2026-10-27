export interface AuthorizationWindow {
  navigate(url: string): boolean;
  focus(): boolean;
  close(): void;
}

export interface AuthorizationBrowser {
  reserve(displayName: string): AuthorizationWindow | null;
}
