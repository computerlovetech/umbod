import { browserTransport, type Transport } from '$lib/admin/infrastructure/transport';
import type { FilesApi as FilesApiPort } from '../api';
import { NodeSharingRoute } from './sharing-route';
import { FilesystemRoute } from './filesystem-route';
import { HttpUploadTransfer, browserOrigin, type OriginProvider } from './upload-transfer';

export class FilesApi implements FilesApiPort {
  readonly filesystem: FilesystemRoute;
  readonly sharing: NodeSharingRoute;

  constructor(transport: Transport, origin: OriginProvider = browserOrigin, externalFetch: typeof globalThis.fetch = globalThis.fetch) {
    this.sharing = new NodeSharingRoute(transport);
    this.filesystem = new FilesystemRoute(transport, new HttpUploadTransfer(transport, origin, externalFetch));
  }
}

export function browserFilesApi(): FilesApiPort {
  return new FilesApi(browserTransport());
}
