export interface AttemptScheduler {
  now(): number;
  schedule(task: () => Promise<void>, delayMs: number): () => void;
}
