import type { SelectOption } from '#lib/components/admin/shared/select-state.svelte.js';

const days = [7, 30, 60, 90] as const;
const never = 'never';
export type TokenExpirationChoice = `${typeof days[number]}` | typeof never;
export const defaultTokenExpiration = '30';
export const tokenExpirationOptions: SelectOption[] = [
  ...days.map((duration): SelectOption => ({ value: String(duration), label: `${duration} days` })),
  { value: never, label: 'Never' }
];

export function isTokenExpirationChoice(choice: string): choice is TokenExpirationChoice {
  return tokenExpirationOptions.some((option) => option.value === choice);
}

export function timestampForTokenExpiration(choice: TokenExpirationChoice, now: number): string | null {
  return choice === never ? null : new Date(now + Number(choice) * 86_400_000).toISOString();
}
