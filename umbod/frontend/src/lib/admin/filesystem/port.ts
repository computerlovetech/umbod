import type { ReplaceRootAccess, RootAccess } from './domain/schemas';

export interface FilesystemAdministration {
  getRootAccess(): Promise<RootAccess>;
  replaceRootAccess(input: ReplaceRootAccess): Promise<RootAccess>;
}
