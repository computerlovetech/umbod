import { Window as TestWindow } from 'happy-dom';
import { afterEach, describe, expect, test, vi } from 'vitest';
import { browserAuthorizationBrowser } from './browser-authorization-browser';

function setup(mobile: boolean, availableWidth = 1920, availableHeight = 1080): { open: ReturnType<typeof vi.fn>; popup: { document: TestWindow['document']; opener: unknown; close: ReturnType<typeof vi.fn> } } {
  const popup = { document: new TestWindow().document, opener: {} as unknown, close: vi.fn<() => void>() };
  const open = vi.fn().mockReturnValue(popup);
  vi.stubGlobal('window', {
    open,
    matchMedia: () => ({ matches: mobile }),
    screen: { availWidth: availableWidth, availHeight: availableHeight },
    screenX: 0,
    screenY: 0,
    outerWidth: availableWidth,
    outerHeight: availableHeight
  });
  return { open, popup };
}

afterEach((): void => { vi.unstubAllGlobals(); });

describe('sign-in loading window', () => {
  test('mobile requests a new tab without desktop popup features', (): void => {
    const { open, popup } = setup(true);
    expect(browserAuthorizationBrowser().reserve('Calendar')).not.toBeNull();
    expect(open).toHaveBeenCalledExactlyOnceWith('about:blank', '_blank');
    expect(popup.opener).toBeNull();
    expect(popup.document.querySelector('h1')?.textContent).toBe('Connecting to Calendar…');
  });

  test('desktop popup fits a smaller available screen', (): void => {
    const { open } = setup(false, 480, 600);
    browserAuthorizationBrowser().reserve('Calendar');
    expect(open).toHaveBeenCalledExactlyOnceWith('about:blank', '_blank', 'popup=yes,width=480,height=600,left=0,top=0');
  });

  test('renders branding, accessible progress and recovery guidance without interpreting provider markup', (): void => {
    const { popup } = setup(false);
    const displayName = '<img src=x onerror=alert(1)>';
    browserAuthorizationBrowser().reserve(displayName);
    expect(popup.document.title).toBe(`Connecting to ${displayName} · Umbod`);
    expect(popup.document.querySelector('h1')?.textContent).toBe(`Connecting to ${displayName}…`);
    expect(popup.document.querySelector('img, script')).toBeNull();
    expect(popup.document.querySelector('[role="status"]')?.getAttribute('aria-live')).toBe('polite');
    expect(popup.document.documentElement.lang).toBe('en');
    expect(popup.document.querySelector('meta[name="viewport"]')?.getAttribute('content')).toBe('width=device-width, initial-scale=1');
    expect(popup.document.body.textContent).toContain('Umbod');
    expect(popup.document.body.textContent).toContain('This window will close automatically');
    expect(popup.document.body.textContent).toContain('return to Umbod to cancel or try again');
    expect(popup.document.querySelector('style')?.textContent).toContain('prefers-reduced-motion');
  });

  test('blocked windows return control to the existing manual sign-in fallback', (): void => {
    const { open } = setup(false);
    open.mockReturnValue(null);
    expect(browserAuthorizationBrowser().reserve('Calendar')).toBeNull();
  });

  test('render failure closes the unused window and preserves fallback', (): void => {
    const { popup } = setup(false);
    vi.spyOn(popup.document.head, 'replaceChildren').mockImplementation((): never => { throw new Error('Unavailable'); });
    expect(browserAuthorizationBrowser().reserve('Calendar')).toBeNull();
    expect(popup.close).toHaveBeenCalledOnce();
  });
});
