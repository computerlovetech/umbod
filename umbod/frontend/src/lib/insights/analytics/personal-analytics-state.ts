import { AnalyticsState } from '#lib/admin/analytics/analytics-state.svelte.js';
import { browserTransport, type Transport } from '#lib/admin/infrastructure/transport.js';
import { PersonalLogCountRoute } from './personal-log-count-route';

export function createPersonalAnalyticsState(
  transport: Transport = browserTransport(),
  now: () => Date = () => new Date()
): AnalyticsState {
  return new AnalyticsState(new PersonalLogCountRoute(transport), now, undefined, {
    accessLostMessage: 'Access to your logs is no longer available. Sign in again to continue.',
    unavailableMessage: 'Personal log analytics is currently unavailable. Try again later.'
  });
}
