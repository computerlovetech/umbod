import { createContext } from 'svelte';
import type { InsightsState } from './insights-state.svelte';

export const [getInsightsState, setInsightsState] = createContext<InsightsState>();
