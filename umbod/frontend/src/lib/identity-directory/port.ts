import type { DirectoryGroups, DirectoryQuery } from './domain/schemas';

export interface IdentityObservation {
  observe(): Promise<void>;
}
export interface IdentityGroupDirectory {
  list(query: DirectoryQuery): Promise<DirectoryGroups>;
}
export interface ObservationEnvironment {
  now(): number;
  visible(): boolean;
  every(milliseconds: number, callback: () => void): () => void;
}
