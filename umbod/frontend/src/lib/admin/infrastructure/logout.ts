import { logoutConfigurationSchema, publicConfigurationProvider, type LogoutConfiguration, type PublicConfigurationProvider } from './public-configuration';

export const gatewayLogoutUrl = '/oauth2/sign_out?rd=%2Fsigned-out.html';

export function buildLogoutUrl(configuration: LogoutConfiguration | null | undefined): string {
  if (configuration == null) return gatewayLogoutUrl;
  const validated = logoutConfigurationSchema.parse(configuration);
  const auth0Url = `https://${validated.auth0Domain}/v2/logout?client_id=${encodeURIComponent(validated.clientId)}&returnTo=${encodeURIComponent(validated.returnTo)}`;
  return `/oauth2/sign_out?rd=${encodeURIComponent(auth0Url)}`;
}

export interface LogoutNavigation {
  logout(): Promise<void>;
}

export class BrowserLogoutNavigation implements LogoutNavigation {
  private pending: Promise<void> | undefined;

  constructor(
    private readonly configuration: PublicConfigurationProvider,
    private readonly assign: (url: string) => void
  ) {}

  logout(): Promise<void> {
    this.pending ??= this.navigate();
    return this.pending;
  }

  private async navigate(): Promise<void> {
    let destination = gatewayLogoutUrl;
    try {
      destination = buildLogoutUrl((await this.configuration.get()).logout);
    } catch {
      destination = gatewayLogoutUrl;
    }
    this.assign(destination);
  }
}

export const logoutNavigation: LogoutNavigation = new BrowserLogoutNavigation(
  publicConfigurationProvider,
  (url: string): void => window.location.assign(url)
);
