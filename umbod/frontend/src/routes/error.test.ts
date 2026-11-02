import { render } from 'svelte/server';
import { Window } from 'happy-dom';
import { afterEach, describe, expect, test, vi } from 'vitest';
import ErrorPage from './+error.svelte';
import { navigateToSignIn } from '$lib/admin/infrastructure/transport';

const state = vi.hoisted(() => ({ page: { status: 401, error: { message: 'private diagnostics and token' } } }));
vi.mock('$app/state', () => state);

afterEach(() => vi.unstubAllGlobals());

describe('root error page', () => {
  test.each([401, 403, 404, 500])('renders safe status %s without automatic navigation', (status) => {
    state.page.status = status;
    const assign = vi.fn();
    vi.stubGlobal('window', { location: { assign } });
    const logout = vi.fn<() => Promise<void>>().mockResolvedValue();
    const { body } = render(ErrorPage, { props: { logout: { logout } } });
    expect(body).toContain(status === 401 || status === 403 ? 'Access denied' : 'Page unavailable');
    expect(body).not.toContain(state.page.error.message);
    const document = new Window().document;
    document.body.innerHTML = body;
    const actions = [...document.querySelectorAll('button')].map((button) => button.textContent);
    expect(actions.includes('Sign in again')).toBe(status === 401);
    if (status === 401) expect(body).toContain('Your sign-in was not accepted by the API.');
    if (status === 403) expect(body).toContain('You do not have permission');
    if (status >= 404) expect(body).toContain('This page could not be loaded.');
    expect(actions.includes('Log out')).toBe(status === 401 || status === 403);
    expect(logout).not.toHaveBeenCalled();
    expect(assign).not.toHaveBeenCalled();
  });

  test('navigates only when the explicit sign-in action is invoked', () => {
    const assign = vi.fn();
    vi.stubGlobal('window', { location: { pathname: '/admin/connectors', search: '?connector=billing', hash: '#tools', assign } });
    expect(assign).not.toHaveBeenCalled();
    navigateToSignIn();
    expect(assign).toHaveBeenCalledExactlyOnceWith('/oauth2/sign_in?rd=%2Fadmin%2Fconnectors%3Fconnector%3Dbilling%23tools');
  });
});
