import type { ActivityChart, ActivityDay } from './types';

export class ActivityTooltip {
  private hoveredDate = $state<string | null>(null);
  private focusedDate = $state<string | null>(null);
  private dismissed = $state(false);

  constructor(private readonly getData: () => ActivityChart) {}

  get day(): ActivityDay | undefined {
    if (this.dismissed || this.getData().total === 0) return undefined;
    const date = this.hoveredDate ?? this.focusedDate;
    return this.getData().days.find((day) => day.date === date);
  }

  get position(): number {
    const days = this.getData().days;
    return (days.findIndex((day) => day.date === this.day?.date) + 0.5) / days.length * 100;
  }

  hover = (date: string): void => {
    this.hoveredDate = date;
    this.dismissed = false;
  };

  leave = (): void => {
    this.hoveredDate = null;
  };

  focus = (date: string): void => {
    this.hoveredDate = null;
    this.focusedDate = date;
    this.dismissed = false;
  };

  blur = (): void => {
    this.focusedDate = null;
  };

  dismiss = (event: KeyboardEvent): void => {
    if (event.key === 'Escape') this.dismissed = true;
  };
}
