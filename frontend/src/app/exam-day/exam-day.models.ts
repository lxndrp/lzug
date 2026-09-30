/** Transport-neutral data used by the examination-day feature. */
export type AttendanceStatus = 'open' | 'present' | 'late' | 'absent';

export type Attendance = { status: AttendanceStatus | string; arrivedAt: string | null };

export type ExecutionStatus =
  'open' | 'running' | 'completed' | 'cancelled' | 'needs_follow_up' | string;

export type ExecutionStatusSummary = Record<
  'open' | 'running' | 'completed' | 'cancelled' | 'needs_follow_up',
  number
>;

export type ExamDayClosureStatus =
  'open' | 'closed' | 'closed_exception' | 'reopening' | 'historical';

export type ExamDayReopeningScopeKind =
  | 'slot_status'
  | 'candidate_attendance'
  | 'member_attendance'
  | 'staffing'
  | 'absence'
  | 'exam_protocol'
  | 'exam_result';

export type ExamDayReopeningScope = { kind: ExamDayReopeningScopeKind; entityId: number };

export type ExamDayClosure = {
  dayId: number;
  revision: number;
  status: ExamDayClosureStatus;
  legacyStatus: string | null;
  evaluation: {
    items: Array<{ code: string; label: string; ok: boolean; details: unknown }>;
    warnings: unknown[];
    regularCloseReady: boolean;
    exceptionCloseReady: boolean;
    exceptionCandidate: unknown | null;
    protocolReferences: Array<{ protocolId?: number; [key: string]: unknown }>;
    resultReferences: Array<{ resultId?: number; [key: string]: unknown }>;
  };
  activeReopening: { expandedScope?: string[]; [key: string]: unknown } | null;
  history: unknown[];
  tasks: unknown[];
  permissions: { close: boolean; reopen: boolean; export: boolean };
  exportLinks: { machine: string; human: string };
};

export type ExamDayReopeningImpact = {
  dayId: number;
  revision: number;
  requestedScope: string[];
  expandedScope: string[];
  impacts: Record<string, number[]>;
};

export type ConfirmedPlanDay = {
  id: number;
  date: string;
  revision: number;
  closureStatus: ExamDayClosureStatus;
  closure: ExamDayClosure;
  location: { id: number; name: string; room: string; city: string } | null;
  slots: Array<{
    id: number;
    startsAt: string;
    endsAt: string;
    sequenceNumber: number;
    slotType: string;
    actualStartedAt: string | null;
    executionStatus: ExecutionStatus;
    statusChangedAt: string;
    actualCompletedAt: string | null;
    statusReason: string | null;
    candidateAttendance: Attendance;
    candidate: { id: number; firstName: string; lastName: string; examNumber: string };
  }>;
  assignments: Array<{
    id: number;
    assignmentRole: string;
    dayPart: string;
    fallbackStatus: string | null;
    attendance: Attendance;
    member: {
      id: number;
      firstName: string;
      lastName: string;
      representingSide: string;
    };
  }>;
  statusSummary: ExecutionStatusSummary;
};

export type ConfirmedPlanDayView = {
  plan: {
    id: number;
    name: string;
    committee: { id: number; name: string };
    examHalfYear: { id: number; season: string; year: number; status: string };
  };
  day: ConfirmedPlanDay;
};

export type SaveAttendanceCommand = {
  dayId: number;
  entityId: number;
  status: AttendanceStatus;
  arrivedAt: string | null;
  dayRevision?: number;
};

export type UpdateExecutionStatusCommand = {
  dayId: number;
  slotId: number;
  status: ExecutionStatus;
  reason?: string;
  dayRevision?: number;
  actualStartedAt?: string | null;
  actualCompletedAt?: string | null;
};

export type CloseExamDayCommand = {
  dayId: number;
  revision: number;
  closureType: 'regular' | 'exception';
  reason: string;
  clarificationAttempts: string;
};

export type ReopenExamDayCommand = {
  dayId: number;
  revision: number;
  occasion: string;
  source: string;
  reason: string;
  scope: ExamDayReopeningScope[];
};
