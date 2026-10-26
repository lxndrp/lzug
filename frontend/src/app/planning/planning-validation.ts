import type { PlanningValidationViolation } from './planning.models';

/** Narrows server supplied validation details before they reach the editor. */
export function planningValidationViolationsFrom(details: unknown): PlanningValidationViolation[] {
  if (!isRecord(details) || !Array.isArray(details['violations'])) return [];
  return details['violations'].filter(isPlanningValidationViolation);
}

function isPlanningValidationViolation(value: unknown): value is PlanningValidationViolation {
  return (
    isRecord(value) &&
    typeof value['code'] === 'string' &&
    typeof value['message'] === 'string' &&
    isNullablePositiveInteger(value['day_id']) &&
    isNullablePositiveInteger(value['slot_id']) &&
    isNullablePositiveInteger(value['member_id'])
  );
}

function isNullablePositiveInteger(value: unknown): value is number | null {
  return value === null || (typeof value === 'number' && Number.isSafeInteger(value) && value > 0);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
