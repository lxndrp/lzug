/** Assessment and result data used by the feature, independent of its API representation. */
export type AssessmentCriterion = {
  key: string;
  label: string;
  rawMin: string;
  rawMax: string;
  weight: string;
};

export type AssessmentComponent = {
  key: string;
  label: string;
  mode: 'committee' | 'independent';
  weight: string;
  dayScoped: boolean;
  requiredAssessors: number;
  maxDeviation: string;
  additionalAssessorOnDeviation: boolean;
  criteria: AssessmentCriterion[];
};

export type ExamResult = {
  id: number;
  roundCandidateId: number;
  dayRevisions?: Record<string, number>;
  version: number;
  state: 'incomplete' | 'calculation_ready' | 'determined' | 'communicated' | string;
  correctionOpen: boolean;
  legacyStatus: string | null;
  candidate: {
    id: number;
    firstName: string;
    lastName: string;
    ihkExamNumber: string;
    specialization: string;
  };
  modelVersion: {
    id: number;
    modelKey: string;
    version: number;
    ihk: string;
    occupation: string;
    specialization: string | null;
    validFrom: string;
    validUntil: string | null;
    rules: {
      components: AssessmentComponent[];
      externalAreas: Array<{ key: string; label: string; weight: string; required: boolean }>;
      rounding: {
        intermediate: { mode: 'none' | 'half_up'; digits: number | null };
        overall: { mode: 'none' | 'half_up'; digits: number | null };
        thresholdBasis: 'unrounded' | 'rounded';
      };
      grades: Array<{ label: string; minPoints: string }>;
      passing: {
        overallMin: string;
        componentMinima: Record<string, string>;
        externalMinima: Record<string, string>;
      };
      quorum: { minimumMembers: number; majority: 'simple' };
    };
    retentionRuleReference: string;
    retentionYears: number;
  };
  participants: number[];
  disclosures: Array<{ componentKey: string; disclosedByMemberId: number; disclosedAt: string }>;
  individualAssessments: Array<{
    id: number;
    componentKey: string;
    criterionKey: string;
    assessorMemberId: number;
    revision: number;
    rawPoints: string;
    normalizedPoints: string;
    rationale: string | null;
    status: 'draft' | 'submitted' | 'withdrawn' | 'superseded';
    changeReason: string | null;
    submittedAt: string | null;
  }>;
  individualAssessmentCounts: Array<{ componentKey: string; draft: number; submitted: number }>;
  committeeAssessments: Array<{
    id: number;
    componentKey: string;
    revision: number;
    points: string;
    rationale: string | null;
    participantMemberIds: number[];
    vote: { yes: number[]; no: number[]; abstain: number[] };
    dissent: Array<{ memberId: number; statement: string }>;
    status: 'current' | 'superseded';
    determinedAt: string;
  }>;
  externalResults: Array<{
    id: number;
    areaKey: string;
    revision: number;
    points: string;
    grade: string | null;
    professionalStatus: string;
    determiningAuthority: string;
    sourceReference: string;
    status: 'unconfirmed' | 'confirmed' | 'replaced';
    recordedByMemberId: number;
    confirmedByMemberId: number | null;
    correctionReason: string | null;
  }>;
  currentCalculation: null | {
    id: number;
    version: number;
    totalPoints: string;
    grade: string;
    passed: boolean;
    path: {
      inputs: Array<{ kind: string; key: string; points: string; weight: string }>;
      unroundedTotal: string;
      roundedTotal: string;
      thresholdBasis: string;
    };
  };
  determinations: Array<{
    id: number;
    revision: number;
    participantMemberIds: number[];
    vote: { yes: number[]; no: number[]; abstain: number[] };
    dissent: Array<{ memberId: number; statement: string }>;
    status: 'current' | 'superseded';
    determinedAt: string;
    confirmationMemberIds: number[];
  }>;
  currentDetermination: ExamResult['determinations'][number] | null;
  corrections: Array<{
    id: number;
    reason: string;
    status: 'open' | 'completed';
    reopeningReference: string | null;
  }>;
  communications: Array<{
    id: number;
    method: string;
    communicatedAt: string;
    externalDocumentStatus: string | null;
    externalDocumentReference: string | null;
    status: 'current' | 'obsolete';
  }>;
  retention: null | {
    ruleReference: string;
    periodStart: string | null;
    retainUntil: string | null;
    legalHold: boolean;
    holdReason: string | null;
  };
  exports: Array<{
    id: number;
    resultDeterminationId: number | null;
    exportKind: 'machine' | 'human';
    status: 'draft' | 'determined' | 'superseded';
    generatedAt: string;
  }>;
  permissions: {
    assessOwn: boolean;
    disclose: boolean;
    determineComponent: boolean;
    manageExternal: boolean;
    determineResult: boolean;
    confirmRecord: boolean;
    coordinateCorrection: boolean;
    communicate: boolean;
    manageRetention: boolean;
  };
  exportsLinks: { machine: string | null; human: string | null };
};

export type SaveIndividualAssessment = {
  resultId: number;
  version: number;
  componentKey: string;
  criterionKey: string;
  rawPoints: string;
  rationale: string;
  submitted: boolean;
  changeReason?: string;
  dayRevisions?: Record<string, number>;
};

export type RecordExternalResult = {
  resultId: number;
  version: number;
  areaKey: string;
  points: string;
  grade?: string;
  professionalStatus: string;
  determiningAuthority: string;
  sourceReference: string;
  correctionReason?: string;
  dayRevisions?: Record<string, number>;
};

export type CommitteeVote = {
  yes: number[];
  no: number[];
  abstain: number[];
};

export type VoteChoice = keyof CommitteeVote;

export type DetermineComponent = {
  resultId: number;
  version: number;
  componentKey: string;
  points: string;
  rationale: string;
  participants: number[];
  vote: CommitteeVote;
  dissent: Array<{ memberId: number; statement: string }>;
  dayRevisions?: Record<string, number>;
};

export type DetermineExamResult = {
  resultId: number;
  version: number;
  participants: number[];
  vote: CommitteeVote;
  dissent: Array<{ memberId: number; statement: string }>;
  dayRevisions?: Record<string, number>;
};

export type SetResultRetention = {
  resultId: number;
  version: number;
  periodStart?: string;
  retainUntil?: string;
  legalHold: boolean;
  holdReason?: string;
  releaseReason?: string;
  dayRevisions?: Record<string, number>;
};
