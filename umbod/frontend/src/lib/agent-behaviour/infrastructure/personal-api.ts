import { browserTransport, type Transport } from '#lib/admin/infrastructure/transport.js';
import type { ReportReadsPort } from '../api';
import { ReportReadsRoute } from './report-reads-route';

export class PersonalAgentBehaviourApi {
  readonly reports: ReportReadsPort;

  constructor(transport: Transport) {
    this.reports = new ReportReadsRoute(transport, '/me/agent-behaviour/reports');
  }
}

export function personalAgentBehaviourApi(fetch?: typeof globalThis.fetch): PersonalAgentBehaviourApi {
  return new PersonalAgentBehaviourApi(browserTransport({ fetch }));
}
