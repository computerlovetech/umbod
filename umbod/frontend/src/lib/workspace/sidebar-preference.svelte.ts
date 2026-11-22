import { getContext, setContext } from 'svelte';

export const sidebarPreferenceKey = Symbol('workspace-sidebar-preference');

export class SidebarPreference {
  #expanded = $state(true);

  get expanded(): boolean {
    return this.#expanded;
  }

  toggle = (): void => {
    this.#expanded = !this.#expanded;
  };
}

export function useSidebarPreference(): SidebarPreference | undefined {
  return getContext<SidebarPreference | undefined>(sidebarPreferenceKey);
}

export function provideSidebarPreference(preference: SidebarPreference): void {
  setContext(sidebarPreferenceKey, preference);
}
