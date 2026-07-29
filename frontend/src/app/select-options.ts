import type { TuiStringHandler } from '@taiga-ui/cdk';

export type SelectOption<T> = Readonly<{
  value: T;
  label: string;
}>;

export function selectValues<T>(options: readonly SelectOption<T>[]): readonly T[] {
  return options.map(({ value }) => value);
}

export function selectLabel<T>(
  options: readonly SelectOption<T>[],
  value: T,
  fallback = '',
): string {
  return options.find((option) => Object.is(option.value, value))?.label ?? fallback;
}

export function selectStringify<T>(options: () => readonly SelectOption<T>[]): TuiStringHandler<T> {
  return (value) => selectLabel(options(), value);
}
