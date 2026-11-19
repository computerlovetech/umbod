export function attachMobileNavigation(panel: HTMLElement): (() => void) | undefined {
  if (typeof panel.hidePopover !== 'function') return;

  const mobile = window.matchMedia('(max-width: 720px)');

  function syncPopover(): void {
    if (!mobile.matches && panel.matches(':popover-open')) panel.hidePopover();
    panel.toggleAttribute('popover', mobile.matches);
  }

  function dismissOnNavigation(event: MouseEvent): void {
    if (!mobile.matches || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target instanceof Element ? event.target.closest('a[href]') : null;
    if (link && panel.matches(':popover-open')) panel.hidePopover();
  }

  panel.querySelector('.mobile-navigation-close button')?.setAttribute('autofocus', '');
  syncPopover();
  mobile.addEventListener('change', syncPopover);
  panel.addEventListener('click', dismissOnNavigation);
  return (): void => {
    mobile.removeEventListener('change', syncPopover);
    panel.removeEventListener('click', dismissOnNavigation);
  };
}
