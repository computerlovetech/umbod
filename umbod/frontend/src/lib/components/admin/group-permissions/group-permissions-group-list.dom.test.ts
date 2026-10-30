import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';
import GroupPermissionsGroupList from './GroupPermissionsGroupList.svelte';

interface Group {
  id: string;
  label: string;
  description: string;
}

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

const groups: Group[] = [
  { id: 'provider:operators', label: 'Platform Operators', description: 'Manage the platform' },
  { id: 'provider:readers', label: 'Readers', description: '' }
];

function target(): HTMLElement {
  const element = document.createElement('div');
  document.body.append(element);
  return element;
}

describe('shared permission group list', () => {
  it('renders labels, descriptions, decorative label initials and accessible selection', (): void => {
    component = mount(GroupPermissionsGroupList<Group>, { target: target(), props: { groups, groupId: (group: Group): string => group.id, selectedGroupId: groups[0].id, onselect: vi.fn() } });
    flushSync();
    const buttons = document.querySelectorAll('button');
    expect(buttons).toHaveLength(2);
    expect(buttons[0].getAttribute('type')).toBe('button');
    expect(buttons[0].getAttribute('aria-current')).toBe('true');
    expect(buttons[1].hasAttribute('aria-current')).toBe(false);
    expect(buttons[0].querySelector('[aria-hidden="true"]')?.textContent).toBe('PO');
    expect(buttons[1].querySelector('[aria-hidden="true"]')?.textContent).toBe('R');
    expect(buttons[0].textContent).toContain('Platform Operators');
    expect(buttons[0].querySelector('small')?.textContent).toBe('Manage the platform');
    expect(buttons[1].querySelector('small')).toBeNull();
  });

  it('delegates selection without optimistically changing the selected group', async (): Promise<void> => {
    const onselect = vi.fn();
    const selection = new SvelteMap<string, string>([['id', groups[0].id]]);
    component = mount(GroupPermissionsGroupList<Group>, { target: target(), props: { groups, groupId: (group: Group): string => group.id, get selectedGroupId(): string { return selection.get('id')!; }, onselect } });
    flushSync();
    const buttons = document.querySelectorAll('button');
    buttons[1].click();
    await tick();
    expect(onselect).toHaveBeenCalledExactlyOnceWith(groups[1].id);
    expect(buttons[0].getAttribute('aria-current')).toBe('true');
    selection.set('id', groups[1].id);
    await tick();
    expect(buttons[0].hasAttribute('aria-current')).toBe(false);
    expect(buttons[1].getAttribute('aria-current')).toBe('true');
  });

  it('updates catalogue labels and handles empty lists and labels', async (): Promise<void> => {
    const catalogue = new SvelteMap<string, Group[]>([['groups', groups]]);
    component = mount(GroupPermissionsGroupList<Group>, { target: target(), props: { get groups(): Group[] { return catalogue.get('groups')!; }, groupId: (group: Group): string => group.id, selectedGroupId: null, onselect: vi.fn() } });
    flushSync();
    const firstButton = document.querySelector('button');
    catalogue.set('groups', [{ ...groups[0], label: 'New name', description: 'Updated' }, { ...groups[1], label: '  ' }]);
    await tick();
    expect(document.querySelector('button')).toBe(firstButton);
    expect(firstButton?.textContent).toContain('New name');
    expect(firstButton?.querySelector('small')?.textContent).toBe('Updated');
    expect(document.querySelectorAll('[aria-hidden="true"]')[1].textContent).toBe('?');
    expect(document.querySelector('[aria-current]')).toBeNull();
    catalogue.set('groups', []);
    await tick();
    expect(document.querySelectorAll('button')).toHaveLength(0);
  });
});
