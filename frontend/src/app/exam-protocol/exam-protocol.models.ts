/** Protocol data and commands used by the feature, independent of its API representation. */
export type ProtocolDeclaration = 'without_special_occurrences' | 'with_special_occurrences';

export type ProtocolEntryCategory =
  | 'late_start'
  | 'interruption'
  | 'termination'
  | 'different_staffing'
  | 'procedural_deviation'
  | 'objection_or_reservation'
  | 'other';

export type ProtocolEntryDraft = {
  category: ProtocolEntryCategory;
  statement: string;
  occurredFrom: string;
  occurredTo: string | null;
};

export type ProtocolEntry = ProtocolEntryDraft & {
  id: number;
  recordedByMemberId: number;
  createdAt: string;
};

export type ProtocolResponse = {
  id: number;
  committeeMemberId: number;
  response: 'confirmed' | 'reservation';
  entryId: number | null;
  statement: string | null;
  respondedAt: string;
};

export type ProtocolRevision = {
  id: number;
  version: number;
  declaration: ProtocolDeclaration | null;
  workflowState: 'draft' | 'submitted' | 'correction_open' | string;
  changeReason: string | null;
  submittedAt: string | null;
  obsolete: boolean;
  missingResponseMemberIds: number[];
  entries: ProtocolEntry[];
  responses: ProtocolResponse[];
};

export type ProtocolCorrectionRequest = {
  id: number;
  version: number;
  requestedByMemberId: number;
  reason: string;
  status: 'pending' | 'opened' | string;
  reopeningReference: string | null;
};

export type ExamProtocol = {
  id: number;
  examSlotId: number;
  dayRevision?: number;
  currentVersion: number;
  state:
    | 'in_progress'
    | 'awaiting_confirmation'
    | 'fully_confirmed'
    | 'fully_with_reservation'
    | 'reaction_missing'
    | 'correction_open'
    | string;
  closingReady: boolean;
  currentRevision: ProtocolRevision;
  history: ProtocolRevision[];
  correctionRequests: ProtocolCorrectionRequest[];
  permissions: {
    edit: boolean;
    submit: boolean;
    respond: boolean;
    requestCorrection: boolean;
    coordinateCorrection: boolean;
    manageRetention: boolean;
  };
  exports: { machineReadable: boolean; humanReadable: boolean };
};

export type UpdateExamProtocol = {
  protocolId: number;
  version: number;
  declaration: ProtocolDeclaration;
  entries: ProtocolEntryDraft[];
  changeReason?: string;
  dayRevision?: number;
};

export type ProtocolExportFormat = 'machine-readable' | 'human-readable';

export type ProtocolExport = {
  content: string;
  mediaType: string;
  fileName: string;
};
