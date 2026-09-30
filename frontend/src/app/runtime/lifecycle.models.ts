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
