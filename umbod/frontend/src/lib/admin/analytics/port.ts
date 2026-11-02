import type { LogCountQuery, LogCountResponse } from './domain/schemas';

export interface LogCountSource {
  query(query: LogCountQuery, signal?: AbortSignal): Promise<LogCountResponse>;
}
