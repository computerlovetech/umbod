import { browserTransport, type Transport } from '$lib/admin/infrastructure/transport';
import type { PersonalAccessTokensApi as ApiPort } from '../api';
import { PersonalAccessTokensRoute } from './tokens-route';

export class PersonalAccessTokensApi implements ApiPort {
  readonly tokens: PersonalAccessTokensRoute;
  constructor(transport: Transport) {
    this.tokens = new PersonalAccessTokensRoute(transport);
  }
}
export function browserPersonalAccessTokensApi(): ApiPort {
  return new PersonalAccessTokensApi(browserTransport());
}
