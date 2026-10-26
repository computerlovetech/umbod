import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { Window } from 'happy-dom';
import { AdminApi } from '../infrastructure/admin-api';
import { AuthenticationRequiredError, HttpError } from '../infrastructure/transport';
import { createBrowserSubmit, type BrowserSubmitDependencies, type BrowserSubmitFunction } from './browser-submit';
import { operationFailure, operationRedirect, type BrowserOperation } from './contracts';
import { OperationState } from './operation-state.svelte';

vi.mock('$app/navigation', () => ({ goto: vi.fn(), invalidateAll: vi.fn() }));

let window: Window;
beforeEach(() => {
  window = new Window();
  vi.stubGlobal('FormData', window.FormData);
});
afterEach(() => { vi.unstubAllGlobals(); });

function fixture(callback?: BrowserSubmitFunction): {
  form: HTMLFormElement;
  button: HTMLButtonElement;
  operation: ReturnType<typeof vi.fn<BrowserOperation>>;
  dependencies: BrowserSubmitDependencies;
  submit: () => void;
  destroy: () => void;
} {
  const form = window.document.createElement('form');
  form.dataset.operation = 'save';
  const input = window.document.createElement('input');
  input.name = 'connectorId'; input.value = 'billing';
  const button = window.document.createElement('button');
  button.type = 'submit';
  form.append(input, button); window.document.body.append(form);
  const operation = vi.fn<BrowserOperation>().mockResolvedValue({ status: 'saved' });
  const dependencies: BrowserSubmitDependencies = {
    operations: { connectors: { save: operation } },
    api: () => new AdminApi({ request: async () => { throw new Error('Unexpected transport request'); } }),
    pathname: () => '/admin/connectors',
    navigate: vi.fn().mockResolvedValue(undefined),
    invalidate: vi.fn().mockResolvedValue(undefined),
    replaceFeedback: vi.fn(),
    flush: vi.fn().mockResolvedValue(undefined)
  };
  const action = createBrowserSubmit(dependencies)(form as unknown as HTMLFormElement, callback);
  return { destroy: action.destroy, form: form as unknown as HTMLFormElement, button: button as unknown as HTMLButtonElement, operation, dependencies, submit: () => { form.dispatchEvent(new window.SubmitEvent('submit', { bubbles: true, cancelable: true, submitter: button })); } };
}

describe('browser submissions', () => {
  test('honors pre-existing submit cancellation', async () => {
    const callback = vi.fn();
    const setup = fixture(callback);
    const event = new window.SubmitEvent('submit', { cancelable: true });
    event.preventDefault(); setup.form.dispatchEvent(event as unknown as SubmitEvent);
    await Promise.resolve();
    expect(callback).not.toHaveBeenCalled(); expect(setup.operation).not.toHaveBeenCalled();
  });
  test('honors callback cancellation and completes pending cleanup', async () => {
    const cleanup = vi.fn();
    const setup = fixture(({ cancel, onComplete }) => { onComplete(cleanup); cancel(); });
    setup.submit(); await vi.waitFor(() => expect(cleanup).toHaveBeenCalledOnce());
    expect(setup.operation).not.toHaveBeenCalled();
  });
  test('uses submitter operations and preserves callback form changes', async () => {
    const setup = fixture(({ formData }) => { formData.set('extra', 'prepared'); });
    setup.button.dataset.operation = 'check';
    setup.dependencies.operations.connectors.check = setup.operation;
    setup.submit(); await vi.waitFor(() => expect(setup.operation).toHaveBeenCalledOnce());
    const submitted = setup.operation.mock.calls[0][1] as FormData;
    expect(submitted.get('connectorId')).toBe('billing'); expect(submitted.get('extra')).toBe('prepared');
  });
  test('contains rejected preparation and completion callbacks and always cleans up', async () => {
    for (const stage of ['prepare', 'after']) {
      const cleanup = vi.fn();
      const setup = fixture(async ({ onComplete }) => {
        onComplete(cleanup);
        if (stage === 'prepare') throw new Error('Preparation failed');
        return async () => { throw new Error('Completion failed'); };
      });
      setup.submit(); await vi.waitFor(() => expect(cleanup).toHaveBeenCalledOnce());
      expect(setup.dependencies.replaceFeedback).toHaveBeenCalledWith(expect.objectContaining({ status: 'failed' }), { route: '/admin/connectors', connectorId: 'billing' });
    }
  });
  test('delivers forbidden and expired authentication results without losing cleanup', async () => {
    for (const cause of [new HttpError(403, 'Forbidden', null), new AuthenticationRequiredError()]) {
      const cleanup = vi.fn(); const after = vi.fn(async ({ update }) => { await update({ reset: false }); });
      const setup = fixture(({ onComplete }) => { onComplete(cleanup); return after; });
      setup.operation.mockRejectedValue(cause);
      setup.submit(); await vi.waitFor(() => expect(cleanup).toHaveBeenCalledOnce());
      expect(after).toHaveBeenCalledWith(expect.objectContaining({ result: expect.objectContaining({ status: cause instanceof HttpError ? 403 : 401 }) }));
      expect(setup.dependencies.invalidate).not.toHaveBeenCalled();
      expect(setup.dependencies.navigate).not.toHaveBeenCalled();
      expect(setup.operation).toHaveBeenCalledOnce();
      expect((setup.form.elements.namedItem('connectorId') as HTMLInputElement).value).toBe('billing');
      setup.submit();
      await vi.waitFor(() => expect(cleanup).toHaveBeenCalledTimes(2));
      expect(setup.operation).toHaveBeenCalledTimes(2);
      expect(setup.dependencies.navigate).not.toHaveBeenCalled();
      expect(setup.dependencies.invalidate).not.toHaveBeenCalled();
    }
  });
  test('navigates redirects without resetting form values', async () => {
    const setup = fixture(); setup.operation.mockResolvedValue(operationRedirect('/admin/connectors?connector=billing'));
    setup.submit(); await vi.waitFor(() => expect(setup.dependencies.navigate).toHaveBeenCalledWith('/admin/connectors?connector=billing'));
    expect(setup.dependencies.replaceFeedback).toHaveBeenCalledWith(null);
  });
  test.each(['disposed', 'selection changed'])('suppresses obsolete completion feedback and reconciliation (%s)', async (scenario) => {
    const cleanup = vi.fn(); const after = vi.fn();
    const setup = fixture(({ onComplete }) => { onComplete(cleanup); return after; });
    let resolve: (value: unknown) => void = () => {};
    setup.operation.mockImplementation(() => new Promise((complete) => { resolve = complete; }));
    let location = '/admin/connectors?connector=billing';
    setup.dependencies.location = () => location;
    setup.submit();
    await vi.waitFor(() => expect(setup.operation).toHaveBeenCalledOnce());
    if (scenario === 'disposed') setup.destroy(); else location = '/admin/connectors?connector=other';
    resolve({ status: 'saved' });
    await vi.waitFor(() => expect(cleanup).toHaveBeenCalledOnce());
    expect(after).not.toHaveBeenCalled();
    expect(setup.dependencies.replaceFeedback).not.toHaveBeenCalled();
    expect(setup.dependencies.invalidate).not.toHaveBeenCalled();
  });
  test.each([
    ['registerPermissionGroup', 'registered'],
    ['deletePermissionGroup', 'deleted'],
    ['saveGroupPermissions', 'saved']
  ])('dispatches %s from nested connector permissions with route-owned feedback', async (name, status): Promise<void> => {
    const setup = fixture();
    const operation = vi.fn<BrowserOperation>().mockResolvedValue({ status, groupId: 'team' });
    setup.dependencies.operations['group-permissions'] = { [name]: operation };
    setup.dependencies.pathname = () => '/admin/group-permissions/connectors';
    setup.form.dataset.operation = name;
    const input = setup.form.elements.namedItem('connectorId') as HTMLInputElement;
    input.name = 'groupId'; input.value = 'team';
    setup.submit();
    await vi.waitFor(() => expect(setup.dependencies.invalidate).toHaveBeenCalledOnce());
    expect(operation).toHaveBeenCalledOnce();
    expect(operation.mock.calls[0][1].get('groupId')).toBe('team');
    expect(setup.operation).not.toHaveBeenCalled();
    expect(setup.dependencies.replaceFeedback).toHaveBeenCalledWith({ status, groupId: 'team' }, { route: '/admin/group-permissions/connectors', connectorId: undefined });
    expect(setup.dependencies.navigate).not.toHaveBeenCalled();
  });
  test('suppresses pending connector permissions feedback after switching to filesystem', async (): Promise<void> => {
    const cleanup = vi.fn(); const after = vi.fn();
    const setup = fixture(({ onComplete }) => { onComplete(cleanup); return after; });
    let pathname = '/admin/group-permissions/connectors';
    setup.dependencies.pathname = () => pathname;
    setup.dependencies.operations['group-permissions'] = { save: setup.operation };
    let complete!: (value: unknown) => void;
    setup.operation.mockImplementation(() => new Promise((resolve) => { complete = resolve; }));
    setup.submit();
    await vi.waitFor(() => expect(setup.operation).toHaveBeenCalledOnce());
    pathname = '/admin/group-permissions/filesystem';
    complete({ status: 'saved', groupId: 'team' });
    await vi.waitFor(() => expect(cleanup).toHaveBeenCalledOnce());
    expect(after).not.toHaveBeenCalled();
    expect(setup.dependencies.replaceFeedback).not.toHaveBeenCalled();
    expect(setup.dependencies.invalidate).not.toHaveBeenCalled();
    expect(setup.dependencies.navigate).not.toHaveBeenCalled();
  });
  test('does not expose completed connector permissions feedback to the filesystem route', async (): Promise<void> => {
    const setup = fixture();
    const feedback = new OperationState();
    const owner = { route: '/admin/group-permissions/connectors', connectorId: 'billing' };
    setup.dependencies.pathname = () => owner.route;
    setup.dependencies.operations['group-permissions'] = { save: setup.operation };
    setup.dependencies.replaceFeedback = feedback.replace;
    setup.submit();
    await vi.waitFor(() => expect(setup.dependencies.invalidate).toHaveBeenCalledOnce());
    expect(feedback.forOwner(owner)).toEqual({ status: 'saved' });
    expect(feedback.forOwner({ ...owner, route: '/admin/group-permissions/filesystem' })).toBeNull();
    feedback.resetForPath('/admin/group-permissions/filesystem');
    expect(feedback.forOwner(owner)).toBeNull();
  });
  test('keeps authoritative failure reconciliation and suppresses invalidation', async () => {
    const setup = fixture(() => async ({ result, update }) => {
      expect(result).toMatchObject({ type: 'failure', status: 409, data: { authoritativeActivationResponse: { tools: [] } } });
      await update({ reset: false, invalidateAll: false });
    });
    setup.operation.mockResolvedValue(operationFailure(409, { status: 'conflict', authoritativeActivationResponse: { tools: [] } }));
    setup.submit(); await vi.waitFor(() => expect(setup.dependencies.replaceFeedback).toHaveBeenCalled());
    expect(setup.dependencies.invalidate).not.toHaveBeenCalled();
  });
});
