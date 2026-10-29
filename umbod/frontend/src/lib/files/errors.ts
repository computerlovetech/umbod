import { AuthenticationRequiredError, HttpError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { z } from 'zod';

export class UploadPhaseError extends Error {
  constructor(readonly phase: 'begin' | 'transfer' | 'complete', readonly cause: unknown) {
    super(cause instanceof Error ? cause.message : 'Upload failed');
    this.name = 'UploadPhaseError';
  }
}

export function uploadCause(error: unknown): unknown {
  return error instanceof UploadPhaseError ? error.cause : error;
}

const filesystemErrorSchema = z.object({ detail: z.object({ code: z.string() }) });

export type FilesPhase = 'loading' | 'ready' | 'denied' | 'sign-in' | 'missing' | 'error';

export function readFailure(error: unknown): FilesPhase {
  if (error instanceof AuthenticationRequiredError) return 'sign-in';
  if (error instanceof HttpError && error.status === 403) return 'denied';
  if (error instanceof HttpError && error.status === 404) return 'missing';
  return 'error';
}

export function uploadFailure(failure: unknown): { message: string; uncertain: boolean; retryable?: boolean } {
  const error = uploadCause(failure);
  if (error instanceof AuthenticationRequiredError) return { message: 'Sign in to upload this file.', uncertain: false };
  if (error instanceof HttpError && error.status === 403) return { message: "You can't upload files here. Your selected file has been kept.", uncertain: false };
  if (error instanceof HttpError && error.status === 409) {
    const body = filesystemErrorSchema.safeParse(error.body);
    const code = body.success ? body.data.detail.code : undefined;
    if (code === 'filesystem_name_collision') return { message: 'A file or folder with that name already exists. Change the file name to upload without overwriting.', uncertain: false };
    if (code === 'filesystem_wrong_node_kind') return { message: 'Choose a folder as the upload destination.', uncertain: false };
    return { message: 'The upload session is no longer ready. Try uploading the file again.', uncertain: false, retryable: true };
  }
  if (error instanceof HttpError && error.status === 410) return { message: 'The upload session expired. Try uploading the file again.', uncertain: false, retryable: true };
  if (error instanceof HttpError && error.status === 413) return { message: 'This file exceeds the current upload limit. Choose a smaller file.', uncertain: false };
  if (error instanceof HttpError && [400, 404, 415, 422].includes(error.status)) return { message: "Couldn't upload this file. Check its name and location.", uncertain: false };
  if (error instanceof SchemaValidationError && error.direction === 'outbound') return { message: 'Check the file and its name before uploading.', uncertain: false };
  if (failure instanceof UploadPhaseError && failure.phase !== 'complete') {
    return { message: failure.phase === 'begin' ? "Couldn't start the upload. Try again." : "Couldn't transfer the file. Try uploading it again.", uncertain: false, retryable: true };
  }
  return { message: "Couldn't confirm the upload. Reload this folder and check its contents before trying again.", uncertain: true };
}

export function folderFailure(error: unknown): { message: string; uncertain: boolean } {
  if (error instanceof AuthenticationRequiredError) return { message: 'Sign in to create a folder.', uncertain: false };
  if (error instanceof HttpError && error.status === 403) return { message: "You can't create a folder here.", uncertain: false };
  if (error instanceof HttpError && error.status === 409) return { message: 'A folder or file with that name already exists.', uncertain: false };
  if (error instanceof HttpError && [400, 404, 422].includes(error.status)) return { message: "Couldn't create the folder. Check its name and location.", uncertain: false };
  return { message: "Couldn't confirm creation. Reload this folder before trying again.", uncertain: true };
}
