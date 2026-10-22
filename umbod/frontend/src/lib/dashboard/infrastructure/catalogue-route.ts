import type { Transport } from '$lib/admin/infrastructure/transport';
import type { CataloguePort } from '../api';
import { userCatalogueSchema, type UserCatalogue } from '../domain/schemas';

export class CatalogueRoute implements CataloguePort {
  constructor(private readonly transport: Transport) {}

  list = (signal?: AbortSignal): Promise<UserCatalogue> => this.transport.request({
    method: 'GET',
    path: '/me/catalogue',
    outputSchema: userCatalogueSchema,
    signal
  });
}
