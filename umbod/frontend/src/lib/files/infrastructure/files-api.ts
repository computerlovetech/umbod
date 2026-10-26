import { browserTransport, type Transport } from '$lib/admin/infrastructure/transport';
import type { FilesApi as FilesApiPort } from '../api';
import { FilesystemRoute } from './filesystem-route';

export class FilesApi implements FilesApiPort {
  readonly filesystem: FilesystemRoute;

  constructor(transport: Transport) {
    this.filesystem = new FilesystemRoute(transport);
  }
}

export function browserFilesApi(): FilesApiPort {
  return new FilesApi(browserTransport());
}
