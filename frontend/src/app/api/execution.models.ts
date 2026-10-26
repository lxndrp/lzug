import type { ApiLink } from './common.models';
import type { RoundStatus } from './planning.models';

/** Half-year fields retained in execution read projections. */
export type ExecutionExamHalfYear = {
  id: number;
  season: string;
  year: number;
  status: string;
};

export type SchedulingStatusGroup = 'draft' | 'coordination' | 'planning' | 'confirmed';

export type SchedulingOverviewItem = {
  id: number;
  name: string;
  status: RoundStatus;
  status_group: SchedulingStatusGroup;
  committee_name: string;
  exam_half_year: ExecutionExamHalfYear;
  calendar_week_from: string | null;
  calendar_week_to: string | null;
  can_continue: boolean;
  _links: Record<string, ApiLink>;
};

export type ConfirmedPlanContext = {
  id: number;
  name: string;
  committee: { id: number; name: string };
  exam_half_year: ExecutionExamHalfYear;
};

export type ConfirmedPlanDay = {
  id: number;
  date: string;
  revision: number;
  closure_status: ExamDayClosureStatus;
  closure: ExamDayClosure;
  location: { id: number; name: string; room: string; city: string } | null;
  slots: Array<{
    id: number;
    starts_at: string;
    ends_at: string;
    sequence_number: number;
    slot_type: 'regular' | 'mep' | string;
    actual_started_at: string | null;
    execution_status: ExecutionStatus;
    status_changed_at: string;
    actual_completed_at: string | null;
    status_reason: string | null;
    candidate_attendance: Attendance;
    candidate: { id: number; first_name: string; last_name: string; ihk_exam_number: string };
  }>;
  assignments: Array<{
    id: number;
    assignment_role: 'examiner' | 'fallback' | string;
    day_part: 'morning' | 'afternoon' | 'full_day' | string;
    fallback_status: 'confirmed' | 'proposed' | null | string;
    attendance: Attendance;
    member: { id: number; first_name: string; last_name: string; representing_side: string };
  }>;
  status_summary: ExecutionStatusSummary;
};

export type ExamDayClosureStatus =
  'open' | 'closed' | 'closed_exception' | 'reopening' | 'historical';

export type ExamDayClosureFinding = {
  code: string;
  label: string;
  ok: boolean;
  details: unknown;
};

export type ExamDayReopeningScopeKind =
  | 'slot_status'
  | 'candidate_attendance'
  | 'member_attendance'
  | 'staffing'
  | 'absence'
  | 'exam_protocol'
  | 'exam_result';

export type ExamDayReopeningScope = {
  kind: ExamDayReopeningScopeKind;
  entity_id: number;
};

export type ExamDayClosure = {
  exam_day_id: number;
  revision: number;
  status: ExamDayClosureStatus;
  legacy_status: string | null;
  evaluation: {
    items: ExamDayClosureFinding[];
    warnings: Array<Record<string, unknown>>;
    regular_close_ready: boolean;
    exception_close_ready: boolean;
    exception_candidate: Record<string, unknown> | null;
    protocol_references: Array<Record<string, unknown>>;
    result_references: Array<Record<string, unknown>>;
  };
  active_reopening: Record<string, unknown> | null;
  history: Array<Record<string, unknown>>;
  tasks: Array<Record<string, unknown>>;
  permissions: { close: boolean; reopen: boolean; export: boolean };
  _links: Record<string, ApiLink>;
};

export type ExamDayReopeningImpact = {
  exam_day_id: number;
  revision: number;
  requested_scope: string[];
  expanded_scope: string[];
  impacts: Record<string, number[]>;
};

export type ExecutionStatus =
  'open' | 'running' | 'completed' | 'cancelled' | 'needs_follow_up' | string;

export type ExecutionStatusSummary = Record<
  'open' | 'running' | 'completed' | 'cancelled' | 'needs_follow_up',
  number
>;

export type AttendanceStatus = 'open' | 'present' | 'late' | 'absent';

export type Attendance = {
  status: AttendanceStatus | string;
  arrived_at: string | null;
};

export type ConfirmedPlan = ConfirmedPlanContext & {
  days: Array<Omit<ConfirmedPlanDay, 'closure'>>;
};

export type ConfirmedPlanDayView = {
  plan: ConfirmedPlanContext;
  day: ConfirmedPlanDay;
  _links: Record<string, ApiLink>;
};
