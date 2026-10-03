import type {
  AvailabilityValue,
  CandidateExamDay,
  PlanningSettings,
  PlanningMemberAvailability,
} from './planning.models';

export type PlanningSettingsPayload = Omit<
  PlanningSettings,
  'id' | 'exam_round_id' | 'updated_by_member_id'
>;
export type CandidateExamDayPayload = Omit<CandidateExamDay, 'id' | 'exam_round_id'>;

export type AvailabilityPayload = Pick<
  PlanningMemberAvailability,
  'committee_member_id' | 'candidate_exam_day_id' | 'availability'
>;

/** One-shot UI effects delivered to the currently active planning view. */
export type PlanningViewEffectCommand =
  | { type: 'reset-candidate-day-draft' }
  | {
      type: 'availability-saved';
      payload: AvailabilityPayload;
      availability: AvailabilityValue;
    }
  | {
      type: 'availability-error';
      payload: AvailabilityPayload;
      usePersistedValue?: boolean;
    };
export type PlanningViewEffect = PlanningViewEffectCommand & { version: number };
