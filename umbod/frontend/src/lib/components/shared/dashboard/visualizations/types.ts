export type OutcomeKey = 'success' | 'failure' | 'cancelled';

export type OutcomeSegment = {
  readonly key: OutcomeKey;
  readonly label: string;
  readonly count: number;
  readonly percentage: number;
  readonly offset: number;
};

export type OutcomeChart = {
  readonly total: number;
  readonly successRate: string;
  readonly segments: readonly OutcomeSegment[];
  readonly label: string;
};

export type OperationSegment = {
  readonly key: 'tool' | 'resource' | 'prompt';
  readonly label: string;
  readonly count: number;
  readonly share: number;
};

export type OperationChart = {
  readonly total: number;
  readonly segments: readonly OperationSegment[];
  readonly label: string;
};

export type ActivityDay = {
  readonly date: string;
  readonly label: string;
  readonly success: number;
  readonly failure: number;
  readonly cancelled: number;
  readonly total: number;
};

export type ActivityChart = {
  readonly days: readonly ActivityDay[];
  readonly axisMaximum: number;
  readonly total: number;
  readonly label: string;
};

export type RankedTool = {
  readonly id: string;
  readonly name: string;
  readonly connector: string;
  readonly count: number;
  readonly barWidth: number;
};
