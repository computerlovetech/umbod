import { AuthenticationRequiredError, HttpError, SchemaValidationError } from '$lib/admin/infrastructure/transport';

export type FilesPhase = 'loading' | 'ready' | 'denied' | 'sign-in' | 'missing' | 'error';

export function readFailure(error: unknown): FilesPhase {
  if (error instanceof AuthenticationRequiredError) return 'sign-in';
  if (error instanceof HttpError && error.status === 403) return 'denied';
  if (error instanceof HttpError && error.status === 404) return 'missing';
  return 'error';
}

export function uploadFailure(error: unknown): { message: string; uncertain: boolean } {
  if (error instanceof AuthenticationRequiredError) return { message: 'Sign in to upload this file.', uncertain: false };
  if (error instanceof HttpError && error.status === 403) return { message: "You can't upload files here. Your selected file has been kept.", uncertain: false };
  if (error instanceof HttpError && error.status === 409) return { message: 'A file or folder with that name already exists. Change the file name to upload without overwriting.', uncertain: false };
  if (error instanceof HttpError && error.status === 413) return { message: 'This file exceeds the current upload limit. Choose a smaller file.', uncertain: false };
  if (error instanceof HttpError && [400, 404, 415, 422].includes(error.status)) return { message: "Couldn't upload this file. Check its name and location.", uncertain: false };
  if (error instanceof SchemaValidationError && error.direction === 'outbound') return { message: 'Check the file and its name before uploading.', uncertain: false };
  return { message: "Couldn't confirm the upload. Reload this folder and check its contents before trying again.", uncertain: true };
}

export function folderFailure(error: unknown): { message: string; uncertain: boolean } {
  if (error instanceof AuthenticationRequiredError) return { message: 'Sign in to create a folder.', uncertain: false };
  if (error instanceof HttpError && error.status === 403) return { message: "You can't create a folder here.", uncertain: false };
  if (error instanceof HttpError && error.status === 409) return { message: 'A folder or file with that name already exists.', uncertain: false };
  if (error instanceof HttpError && [400, 404, 422].includes(error.status)) return { message: "Couldn't create the folder. Check its name and location.", uncertain: false };
  return { message: "Couldn't confirm creation. Reload this folder before trying again.", uncertain: true };
}
