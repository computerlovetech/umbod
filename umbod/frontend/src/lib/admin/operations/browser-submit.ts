import { goto, invalidateAll } from '$app/navigation';
import { tick } from 'svelte';
import { adminApi, type AdminApi } from '../infrastructure/admin-api';
import { AuthenticationRequiredError, HttpError } from '../infrastructure/transport';
import { connectorsOperations } from './connectors';
import { downstreamMcpConnectorsOperations } from './downstream-mcp-connectors';
import { openApiConnectorsOperations } from './openapi-connectors';
import { groupPermissionsOperations } from './group-permissions';
import { OperationFailure, OperationRedirect, type BrowserOperations } from './contracts';
import { operationState, type FeedbackOwner } from './operation-state.svelte';

export type BrowserOperationResult =
  | { type: 'success' | 'failure'; status: number; data: Record<string, unknown> }
  | { type: 'redirect'; status: number; location: string }
  | { type: 'error'; status: number; error: Error };
export type BrowserSubmitUpdate = (options?: { reset?: boolean; invalidateAll?: boolean }) => Promise<void>;
export type BrowserSubmitAfter = (input: { result: BrowserOperationResult; update: BrowserSubmitUpdate }) => void | Promise<void>;
export type BrowserSubmitFunction = (input: {
  formData: FormData;
  formElement: HTMLFormElement;
  submitter: HTMLElement | null;
  cancel: () => void;
  onComplete: (cleanup: () => void) => void;
}) => void | BrowserSubmitAfter | Promise<void | BrowserSubmitAfter>;

export interface BrowserSubmitDependencies {
  operations: Record<string, BrowserOperations>;
  api: () => AdminApi;
  pathname: () => string;
  location?: () => string;
  navigate: (location: string) => Promise<void>;
  invalidate: () => Promise<void>;
  replaceFeedback: (data: Record<string, unknown> | null, owner?: FeedbackOwner) => void;
  flush: () => Promise<void>;
}

type BrowserSubmitAction = (form: HTMLFormElement, callback?: BrowserSubmitFunction) => { destroy: () => void; update: (next?: BrowserSubmitFunction) => void };

function errorResult(cause: unknown): BrowserOperationResult {
  if (cause instanceof HttpError) return { type: 'failure', status: cause.status, data: { status: 'failed', message: cause.message, errorMessage: cause.message } };
  return { type: 'error', status: cause instanceof AuthenticationRequiredError ? 401 : 500, error: cause instanceof Error ? cause : new Error('Operation failed') };
}

function operationResult(value: unknown): BrowserOperationResult {
  if (value instanceof OperationFailure) return { type: 'failure', status: value.status, data: value.data };
  if (value instanceof OperationRedirect) return { type: 'redirect', status: 303, location: value.location };
  return { type: 'success', status: 200, data: value as Record<string, unknown> };
}

export function createBrowserSubmit(dependencies: BrowserSubmitDependencies): BrowserSubmitAction {
  return (form, callback) => {
    let currentCallback = callback;
    let submitting = false;
    let disposed = false;
    const run = async (event: SubmitEvent): Promise<void> => {
      if (event.defaultPrevented) return;
      event.preventDefault();
      if (submitting) return;
      submitting = true;
      const cleanups: Array<() => void> = [];
      const initialLocation = (dependencies.location ?? dependencies.pathname)();
      const owner: FeedbackOwner = { route: dependencies.pathname() };
      const isCurrent = (): boolean => !disposed && form.isConnected && (dependencies.location ?? dependencies.pathname)() === initialLocation;
      let after: void | BrowserSubmitAfter = undefined;
      let result: BrowserOperationResult;
      const update: BrowserSubmitUpdate = async (options = {}) => {
        if (!isCurrent()) return;
        if (result.type === 'redirect') { dependencies.replaceFeedback(null); await dependencies.navigate(result.location); return; }
        if (result.type === 'error') {
          dependencies.replaceFeedback({ status: 'failed', message: result.error.message, errorMessage: result.error.message }, owner);
          await dependencies.flush();
          return;
        }
        dependencies.replaceFeedback(result.data, owner);
        await dependencies.flush();
        if (result.type === 'success') {
          if (options.reset !== false) form.reset();
          if (options.invalidateAll !== false) await dependencies.invalidate();
        }
      };
      try {
        const submitter = event.submitter;
        const formData = new FormData(form, submitter);
        owner.connectorId = String(formData.get('connectorId') ?? '') || undefined;
        let cancelled = false;
        try {
          after = await currentCallback?.({ formData, formElement: form, submitter, cancel: () => { cancelled = true; }, onComplete: (cleanup) => cleanups.push(cleanup) });
          if (cancelled || !isCurrent()) return;
          const context = dependencies.pathname().split('/')[2];
          const name = submitter?.dataset.operation ?? form.dataset.operation ?? 'saveConfiguration';
          const operation = dependencies.operations[context]?.[name];
          if (!operation) throw new Error(`Unknown browser operation: ${context}.${name}`);
          result = operationResult(await operation(dependencies.api(), formData));
        } catch (cause) { result = errorResult(cause); }
        if (!isCurrent()) return;
        try { if (after) await after({ result, update }); else await update(); }
        catch (cause) { result = errorResult(cause); await update(); }
      } catch (cause) {
        const failure = errorResult(cause);
        if (isCurrent()) dependencies.replaceFeedback(failure.type === 'error' ? { status: 'failed', message: failure.error.message } : { status: 'failed', message: 'Operation could not be completed' }, owner);
      } finally {
        submitting = false;
        for (const cleanup of cleanups) { try { cleanup(); } catch { if (isCurrent()) dependencies.replaceFeedback({ status: 'failed', message: 'Submission feedback could not be updated' }, owner); } }
      }
    };
    const onSubmit = (event: SubmitEvent): void => { void run(event); };
    form.addEventListener('submit', onSubmit);
    return { destroy: () => { disposed = true; form.removeEventListener('submit', onSubmit); }, update: (next) => { currentCallback = next; } };
  };
}

export const browserSubmit: BrowserSubmitAction = createBrowserSubmit({
  operations: { connectors: connectorsOperations, 'downstream-mcp-connectors': downstreamMcpConnectorsOperations, 'openapi-connectors': openApiConnectorsOperations, 'group-permissions': groupPermissionsOperations },
  api: () => adminApi(),
  pathname: () => window.location.pathname,
  location: () => `${window.location.pathname}${window.location.search}`,
  navigate: (location) => goto(location, { invalidateAll: true }),
  invalidate: invalidateAll,
  replaceFeedback: operationState.replace,
  flush: tick
});
