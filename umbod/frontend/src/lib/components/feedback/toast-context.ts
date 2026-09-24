import { createContext } from 'svelte';
import type { ToastApi } from './toast-state.svelte';

export const [useToast, provideToast] = createContext<ToastApi>();
