export type SelectOption = {
  value: string;
  label: string;
  disabled?: boolean;
};

export type SelectOverlayGeometry = {
  left: number;
  top: number;
  width: number;
  maxHeight: number;
  placement: 'above' | 'below';
};

export type SelectViewport = {
  width: number;
  height: number;
  offsetLeft: number;
  offsetTop: number;
};

const overlayGap = 4;
const viewportMargin = 8;
const minimumUsefulHeight = 96;
const preferredMaximumHeight = 288;

export function calculateSelectOverlayGeometry(trigger: Pick<DOMRect, 'left' | 'top' | 'right' | 'bottom' | 'width'>, viewport: SelectViewport, overlayHeight: number): SelectOverlayGeometry {
  const viewportLeft = viewport.offsetLeft;
  const viewportTop = viewport.offsetTop;
  const viewportRight = viewportLeft + viewport.width;
  const viewportBottom = viewportTop + viewport.height;
  const width = Math.min(trigger.width, Math.max(0, viewport.width - viewportMargin * 2));
  const left = Math.min(Math.max(trigger.left, viewportLeft + viewportMargin), viewportRight - viewportMargin - width);
  const availableBelow = Math.max(0, viewportBottom - trigger.bottom - overlayGap - viewportMargin);
  const availableAbove = Math.max(0, trigger.top - viewportTop - overlayGap - viewportMargin);
  const placement = availableBelow >= minimumUsefulHeight || availableBelow >= availableAbove ? 'below' : 'above';
  const maxHeight = Math.min(preferredMaximumHeight, overlayHeight, placement === 'below' ? availableBelow : availableAbove);
  const top = placement === 'below' ? trigger.bottom + overlayGap : trigger.top - overlayGap - maxHeight;
  return { left, top, width, maxHeight, placement };
}

export class SelectState {
  isOpen = $state(false);
  activeValue = $state<string | undefined>(undefined);
  selectedValue = $state('');
  overlayGeometry = $state<SelectOverlayGeometry | undefined>(undefined);
  readonly options: SelectOption[];

  constructor(options: SelectOption[], value: string) {
    this.options = options;
    this.selectedValue = value;
  }

  get selectedOption(): SelectOption | undefined {
    return this.options.find((option) => option.value === this.selectedValue);
  }

  open = (): void => {
    this.isOpen = true;
    const selected = this.options.find((option) => option.value === this.selectedValue && !option.disabled);
    this.activeValue = selected?.value ?? this.enabledOptions[0]?.value;
  };

  close = (): void => {
    this.isOpen = false;
    this.activeValue = undefined;
    this.overlayGeometry = undefined;
  };

  toggle = (): void => {
    if (this.isOpen) this.close();
    else this.open();
  };

  setOverlayGeometry = (geometry: SelectOverlayGeometry): void => {
    this.overlayGeometry = geometry;
  };

  select = (value: string): string | undefined => {
    const option = this.options.find((candidate) => candidate.value === value);
    if (!option || option.disabled) return undefined;
    this.selectedValue = option.value;
    this.close();
    return option.value;
  };

  moveNext = (): void => this.move(1);
  movePrevious = (): void => this.move(-1);

  setActive = (value: string): void => {
    const option = this.options.find((candidate) => candidate.value === value);
    if (option && !option.disabled) this.activeValue = value;
  };

  moveFirst = (): void => {
    this.activeValue = this.enabledOptions[0]?.value;
  };

  moveLast = (): void => {
    this.activeValue = this.enabledOptions.at(-1)?.value;
  };

  private get enabledOptions(): SelectOption[] {
    return this.options.filter((option) => !option.disabled);
  }

  private move(direction: 1 | -1): void {
    const enabledOptions = this.enabledOptions;
    if (enabledOptions.length === 0) return;
    const currentIndex = enabledOptions.findIndex((option) => option.value === this.activeValue);
    const nextIndex = currentIndex < 0 ? (direction === 1 ? 0 : enabledOptions.length - 1) : (currentIndex + direction + enabledOptions.length) % enabledOptions.length;
    this.activeValue = enabledOptions[nextIndex].value;
  }
}
