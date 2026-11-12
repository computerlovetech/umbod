export class VisualizationProps<T> {
  private currentValue: T;

  constructor(value: T) {
    this.currentValue = $state.raw(value);
  }

  get value(): T { return this.currentValue; }

  replace = (value: T): void => {
    this.currentValue = value;
  };
}
