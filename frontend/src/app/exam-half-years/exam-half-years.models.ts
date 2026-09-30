export type ExamHalfYear = {
  id: number;
  season: 'summer' | 'winter';
  year: number;
  status: string;
};

export type ExamRound = {
  id: number;
  halfYearId: number;
  name: string;
  committeeId: number;
  status: string;
};

export type CommitteeOption = { id: number; name: string };
export type CandidateOption = { id: number; firstName: string; lastName: string };
export type CandidateAssignment = {
  halfYearId: number;
  candidateId: number;
  endedAt: string | null;
};

export type CreateExamRound = {
  committeeId: number;
  name: string;
} & (
  | { halfYearId: number; season?: never; year?: never }
  | { halfYearId?: never; season: ExamHalfYear['season']; year: number }
);

export type RoundLifecycle = {
  roundId: number;
  revision: number;
  status: string;
  historicalWithoutFormalEvidence: boolean;
  evaluation: { ready: boolean; items: Array<{ code: string; label: string; ok: boolean }> };
  candidates: Array<{
    roundCandidateId: number;
    candidateId: number;
    terminalStatus: string;
  }>;
  retention: { retainUntil: string | null; legalHold: boolean };
  ihkStatuses: Array<{
    id: number;
    examResultId: number;
    documentStatus: string;
    documentReference: string;
  }>;
  permissions: { close: boolean; cancel: boolean; reopen: boolean; delete: boolean };
  history: Array<{ id: number; roundRevision: number; eventType: string; reason: string | null }>;
};

export type RoundCandidateTerminalStatus = {
  revision: number;
  terminalStatus: string;
  reason?: string;
  effectiveNewRoundId?: number;
  postponedUntil?: string;
  ihkDecisionReference?: string;
};

export type RoundReopening = {
  revision: number;
  occasion: string;
  source: string;
  reason: string;
  scope: Array<{ kind: string; entityId: number }>;
};

export type LifecycleExportFormat = 'json' | 'text';
export type LifecycleExport = { content: string; mediaType: string; fileName: string };
