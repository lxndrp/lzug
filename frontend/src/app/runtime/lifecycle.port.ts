import { InjectionToken } from '@angular/core';

import type { LifecycleState } from './lifecycle.models';

export interface LifecycleAvailabilityPort {
  isReady(): boolean;
  currentState(): LifecycleState | 'unreachable';
  acceptUnavailable(state: LifecycleState | 'unreachable'): void;
}

export const LIFECYCLE_AVAILABILITY_PORT = new InjectionToken<LifecycleAvailabilityPort>(
  'LIFECYCLE_AVAILABILITY_PORT',
);
