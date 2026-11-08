import { dimensions, logCountQuerySchema, type Dimension, type LogCountQuery } from './domain/schemas';

export const dimensionLabels: Record<Dimension, string> = {
  source: 'Source', event_name: 'Event name', severity: 'Severity', session_id: 'Session ID', tool_name: 'Tool name', activity_kind: 'Activity kind', outcome: 'Outcome'
};
export const dimensionOptions = dimensions.map((dimension) => ({ value: dimension, label: dimensionLabels[dimension] }));
export const rangeOptions = [
  { value: 'hour', label: 'Last hour' }, { value: 'day', label: 'Last 24 hours' },
  { value: 'week', label: 'Last 7 days' }, { value: 'custom', label: 'Custom range' }
];
export const bucketOptions = [
  { value: 'none', label: 'Total for range' }, { value: 'minute', label: 'Minute' },
  { value: 'hour', label: 'Hour' }, { value: 'day', label: 'Day' }
];
export type RangePreset = 'hour' | 'day' | 'week' | 'custom';
export type BucketWidth = 'none' | 'minute' | 'hour' | 'day';

export class QueryDraft {
  private presetValue = $state<RangePreset>('hour');
  private startValue = $state('');
  private endValue = $state('');
  private offsetValue = $state('+00:00');
  private bucketValue = $state<BucketWidth>('none');
  private grouping = $state.raw<readonly Dimension[]>(['severity']);
  private filterValues = $state.raw<Record<Dimension, readonly string[]>>({ source: [], event_name: [], severity: [], session_id: [], tool_name: [], activity_kind: [], outcome: [] });

  get preset(): RangePreset { return this.presetValue; }
  get start(): string { return this.startValue; }
  get end(): string { return this.endValue; }
  get offset(): string { return this.offsetValue; }
  get bucket(): BucketWidth { return this.bucketValue; }
  get groupBy(): readonly Dimension[] { return this.grouping; }
  get filters(): Readonly<Record<Dimension, readonly string[]>> { return this.filterValues; }
  get fingerprint(): string {
    return JSON.stringify([this.preset, this.start, this.end, this.offset, this.bucket, this.groupBy, this.filters]);
  }
  setPreset(value: string): void { if (rangeOptions.some((option) => option.value === value)) this.presetValue = value as RangePreset; }
  setStart(value: string): void { this.startValue = value; }
  setEnd(value: string): void { this.endValue = value; }
  setOffset(value: string): void { this.offsetValue = value; }
  setBucket(value: string): void { if (bucketOptions.some((option) => option.value === value)) this.bucketValue = value as BucketWidth; }
  selectFilter(dimension: Dimension, value: string): void {
    if (!this.filterValues[dimension].includes(value)) this.filterValues = { ...this.filterValues, [dimension]: [...this.filterValues[dimension], value] };
  }
  removeFilter(dimension: Dimension, value: string): void {
    this.filterValues = { ...this.filterValues, [dimension]: this.filterValues[dimension].filter((entry) => entry !== value) };
  }
  toggleGroup(dimension: Dimension): void {
    this.grouping = this.grouping.includes(dimension) ? this.grouping.filter((entry) => entry !== dimension) : [...this.grouping, dimension];
  }
  resolveTimeRange(now: Date): LogCountQuery['time_range'] {
    const durations = { hour: 3600000, day: 86400000, week: 604800000 };
    const time_range = this.presetValue === 'custom'
      ? { start: this.customInstant(this.start), end: this.customInstant(this.end) }
      : { start: new Date(now.getTime() - durations[this.presetValue]).toISOString(), end: now.toISOString() };
    const result = logCountQuerySchema.shape.time_range.safeParse(time_range);
    if (!result.success) throw new Error('Choose a valid range with start before end.');
    return result.data;
  }
  resolve(now: Date): LogCountQuery {
    const result = logCountQuerySchema.safeParse({
      time_range: this.resolveTimeRange(now),
      filters: dimensions.filter((dimension) => this.filters[dimension].length > 0).map((dimension) => ({ dimension, values: [...this.filters[dimension]] })),
      group_by: [...this.groupBy],
      bucketing: this.bucket === 'none' ? { kind: 'none' } : { kind: 'fixed', width: this.bucket },
      pagination: { limit: 100, offset: 0 }
    });
    if (!result.success) throw new Error('Choose a valid range with start before end.');
    return result.data;
  }
  private customInstant(value: string): string {
    if (!/^[+-](?:0\d|1[0-4]):[0-5]\d$/.test(this.offset) || (this.offset.slice(1, 3) === '14' && this.offset.slice(4) !== '00')) throw new Error('Enter a UTC offset between −14:00 and +14:00.');
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(value)) throw new Error('Enter both custom dates and times.');
    const parsed = logCountQuerySchema.shape.time_range.shape.start.safeParse(`${value.length === 16 ? value + ':00' : value}${this.offset}`);
    if (!parsed.success) throw new Error('Enter valid custom dates and times.');
    return new Date(parsed.data).toISOString();
  }
}
