export class FolderPickerFocusState {
  private focusedId = $state<string | undefined>(undefined);

  isFocused = (id: string): boolean => this.focusedId === id;
  focus = (id: string): void => { this.focusedId = id; };
  blur = (id: string): void => { if (this.focusedId === id) this.focusedId = undefined; };
}
