/** Public state codes shared with the runtime lifecycle feature. */
export const lifecycleStates = [
  'initializing',
  'ready',
  'maintenance',
  'migration_required',
  'migrating',
  'error',
  'stopping',
  'stopped',
] as const;

export type LifecycleState = (typeof lifecycleStates)[number];

export function isLifecycleState(value: unknown): value is LifecycleState {
  return typeof value === 'string' && lifecycleStates.some((state) => state === value);
}

export function lifecycleStateFrom(payload: unknown): LifecycleState | null {
  if (!isRecord(payload)) return null;
  const state = payload['state'];
  if (!isLifecycleState(state)) return null;
  return payload['ready'] === (state === 'ready') ? state : null;
}

export function unavailableLifecycleStateFrom(payload: unknown): LifecycleState | null {
  if (
    !isRecord(payload) ||
    payload['code'] !== 'runtime_not_ready' ||
    payload['ready'] !== false ||
    !isLifecycleState(payload['state'])
  ) {
    return null;
  }
  return payload['state'];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
