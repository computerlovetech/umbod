import { flushSync, mount, unmount } from 'svelte';
import { expect, test, vi } from 'vitest';
import AdminToggle from './AdminToggle.svelte';

test.each([false, true])('the submit switch preserves form activation with disabled=%s', async (disabled: boolean): Promise<void> => {
  const form = document.createElement('form');
  const submit = vi.fn((event: Event): void => event.preventDefault());
  form.addEventListener('submit', submit);
  document.body.append(form);
  const component = mount(AdminToggle, {
    target: form,
    props: { checked: true, ariaLabel: 'Enable connector', disabled, submit: true }
  });
  try {
    flushSync();
    const control = form.querySelector<HTMLButtonElement>('button[role="switch"]');
    expect(control).toBeInstanceOf(HTMLButtonElement);
    expect(control?.type).toBe('submit');
    expect(control?.getAttribute('aria-checked')).toBe('true');
    expect(control?.getAttribute('aria-label')).toBe('Enable connector');
    control?.click();
    expect(submit).toHaveBeenCalledTimes(disabled ? 0 : 1);
  } finally {
    await unmount(component);
    form.remove();
  }
});
