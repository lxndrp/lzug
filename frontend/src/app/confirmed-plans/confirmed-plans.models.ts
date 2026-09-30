/** Feature data for a confirmed plan, independent of its API representation. */
export type ConfirmedPlan = {
  id: number;
  name: string;
  committee: { id: number; name: string };
  examHalfYear: { id: number; season: string; year: number; status: string };
  days: ConfirmedPlanDay[];
};

export type ConfirmedPlanDay = {
  id: number;
  date: string;
  revision: number;
  closureStatus: string;
  location: { id: number; name: string; room: string; city: string } | null;
  slots: Array<{
    id: number;
    startsAt: string;
    endsAt: string;
    sequenceNumber: number;
    slotType: string;
    actualStartedAt: string | null;
    executionStatus: string;
    statusChangedAt: string;
    actualCompletedAt: string | null;
    statusReason: string | null;
    candidateAttendance: { status: string; arrivedAt: string | null };
    candidate: { id: number; firstName: string; lastName: string; examNumber: string };
  }>;
  assignments: Array<{
    id: number;
    assignmentRole: string;
    dayPart: string;
    fallbackStatus: string | null;
    attendance: { status: string; arrivedAt: string | null };
    member: { id: number; firstName: string; lastName: string; representingSide: string };
  }>;
  statusSummary: Record<string, number>;
};

export type EditableConfirmedPlan = {
  roundId: number;
  revision: number;
  days: EditableConfirmedPlanDay[];
};

export type EditableConfirmedPlanDay = {
  candidateDayId: number;
  id: number | null;
  date: string;
  roomId?: number;
  locationId: number;
  status: string;
  slots: EditableConfirmedPlanSlot[];
  assignments: EditableConfirmedPlanAssignment[];
};

export type EditableConfirmedPlanSlot = {
  roundCandidateId: number;
  id: number | null;
  slotType: 'regular' | 'mep';
  startsAt: string;
  endsAt: string;
  sequenceNumber: number;
  status: string;
};

export type EditableConfirmedPlanAssignment = {
  committeeMemberId: number;
  id: number | null;
  assignmentRole: 'examiner' | 'fallback';
  dayPart: 'morning' | 'afternoon' | 'full_day';
  fallbackStatus: string | null;
};

export type ConfirmedPlanRevision = {
  id: number;
  previousRevision: number;
  resultingRevision: number;
  reason: string;
  actorMemberId: number;
  createdAt: string;
  before: EditableConfirmedPlan;
  after: EditableConfirmedPlan;
};

/** Small projection needed by the editor to render its selectable references. */
export type ConfirmedPlansBoard = {
  candidates: Array<{
    roundCandidateId: number;
    firstName: string;
    lastName: string;
    examNumber: string;
  }>;
  members: Array<{ id: number; firstName: string; lastName: string }>;
  locations: Array<{ id: number; name: string; room: string; city: string }>;
};

export type PreparedConfirmedPlanChange = {
  roundId: number;
  dayId: number;
  sourceLocationId: number;
  targetLocationId: number;
  assignmentId: number;
  replacementMemberId: number;
  reason: string;
};
