import type { AdminApi } from '../infrastructure/admin-api';

export class OperationFailure<T extends Record<string, unknown>> {
  constructor(readonly status: number, readonly data: T) {}
}
export class OperationRedirect {
  constructor(readonly location: string) {}
}
export function operationFailure<T extends Record<string, unknown>>(status: number, data: T): OperationFailure<T> {
  return new OperationFailure(status, data);
}
export function operationRedirect(location: string): OperationRedirect { return new OperationRedirect(location); }
export type BrowserOperation = (api: AdminApi, data: FormData) => Promise<unknown>;
export type BrowserOperations = Record<string, BrowserOperation>;
