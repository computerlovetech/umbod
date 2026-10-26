import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';

export type FilesPhase = 'loading' | 'ready' | 'denied' | 'sign-in' | 'missing' | 'error';

export function readFailure(error: unknown): FilesPhase {
  if (error instanceof AuthenticationRequiredError) return 'sign-in';
  if (error instanceof HttpError && error.status === 403) return 'denied';
  if (error instanceof HttpError && error.status === 404) return 'missing';
  return 'error';
}

export function folderFailure(error: unknown): { message: string; uncertain: boolean } {
  if (error instanceof AuthenticationRequiredError) return { message: 'Sign in to create a folder.', uncertain: false };
  if (error instanceof HttpError && error.status === 403) return { message: "You can't create a folder here.", uncertain: false };
  if (error instanceof HttpError && error.status === 409) return { message: 'A folder or file with that name already exists.', uncertain: false };
  if (error instanceof HttpError && [400, 404, 422].includes(error.status)) return { message: "Couldn't create the folder. Check its name and location.", uncertain: false };
  return { message: "Couldn't confirm creation. Reload this folder before trying again.", uncertain: true };
}
