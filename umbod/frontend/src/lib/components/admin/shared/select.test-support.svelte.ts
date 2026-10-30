import type { SelectOption } from './select-state.svelte';

export class SelectTestModel {
  private choices = $state<SelectOption[]>([
    { value: ' first value ', label: 'First choice' },
    { value: 'disabled', label: 'Disabled choice', disabled: true },
    { value: 'second', label: 'Second choice' }
  ]);
  private selected = $state('');
  private query = $state('');
  private blocked = $state(false);
  private inherited = $state(false);
  readonly selections: string[] = [];

  get options(): SelectOption[] { return this.choices; }
  get value(): string { return this.selected; }
  get disabled(): boolean { return this.blocked; }
  get fieldsetDisabled(): boolean { return this.inherited; }
  get search(): { value: string; oninput: (value: string) => void; placeholder: string } {
    return { value: this.query, oninput: this.input, placeholder: 'Find a choice' };
  }

  input = (value: string): void => {
    this.query = value;
    this.choices = value === 'empty' ? [] : [{ value: 'filtered value', label: `Result ${value}` }];
  };

  select = (value: string): void => {
    this.selections.push(value);
    this.selected = value;
    this.query = '';
  };

  replace = (options: SelectOption[], value: string): void => {
    this.choices = options;
    this.selected = value;
  };

  disable = (inherited: boolean = false): void => {
    if (inherited) this.inherited = true;
    else this.blocked = true;
  };
}
