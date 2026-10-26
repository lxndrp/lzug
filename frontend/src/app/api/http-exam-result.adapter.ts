import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { catchError, map, throwError } from 'rxjs';

import type {
  ExamResultResponse as ApiExamResult,
  IndividualAssessmentRequest,
} from './generated/types.gen';
import { ApiClient } from './api-client.service';
import { toApplicationError } from './application-error';
import type { FileDownload } from '../application/file-download';
import type {
  DetermineComponent,
  DetermineExamResult,
  ExamResult,
  ExamResultExportFormat,
  RecordExternalResult,
  SaveIndividualAssessment,
  SetResultRetention,
} from '../exam-result/exam-result.models';
import type { ExamResultPort } from '../exam-result/exam-result.port';

/** HTTP/OpenAPI adapter for the transport-neutral exam-result feature port. */
@Injectable({ providedIn: 'root' })
export class HttpExamResultAdapter implements ExamResultPort {
  private readonly client = inject(ApiClient);
  private readonly http = inject(HttpClient);

  export(resultId: number, format: ExamResultExportFormat) {
    const extension = format === 'machine-readable' ? 'json' : 'txt';
    return this.http
      .get(`/api/exam-results/${resultId}/export.${extension}`, {
        observe: 'response',
        responseType: 'text',
      })
      .pipe(
        map((response): FileDownload => ({
          content: response.body ?? '',
          mediaType:
            response.headers.get('content-type') ??
            (format === 'machine-readable'
              ? 'application/json; charset=utf-8'
              : 'text/plain; charset=utf-8'),
          fileName:
            response.headers.get('content-disposition')?.match(/filename="?([^";]+)"?/i)?.[1] ??
            `pruefungsergebnis-${resultId}.${extension}`,
        })),
        catchError((error: unknown) => throwError(() => toApplicationError(error))),
      );
  }

  get(dayId: number, slotId: number) {
    return this.client
      .get<ApiExamResult>(`/api/confirmed-plan-days/${dayId}/slots/${slotId}/result`)
      .pipe(map(fromApiResult));
  }

  saveIndividualAssessment(command: SaveIndividualAssessment) {
    const body = {
      version: command.version,
      component_key: command.componentKey,
      criterion_key: command.criterionKey,
      raw_points: command.rawPoints,
      rationale: command.rationale.trim() || null,
      submitted: command.submitted,
      ...(command.changeReason?.trim() ? { change_reason: command.changeReason.trim() } : {}),
      ...(command.dayRevisions ? { day_revisions: command.dayRevisions } : {}),
    } satisfies IndividualAssessmentRequest;
    return this.client
      .post<ApiExamResult>(`/api/exam-results/${command.resultId}/individual-assessments`, body)
      .pipe(map(fromApiResult));
  }

  withdrawIndividualAssessment(
    resultId: number,
    version: number,
    assessmentId: number,
    reason: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client
      .post<ApiExamResult>(
        `/api/exam-results/${resultId}/individual-assessments/${assessmentId}/withdraw`,
        {
          version,
          reason: reason.trim(),
          ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
        },
      )
      .pipe(map(fromApiResult));
  }

  discloseAssessments(
    resultId: number,
    version: number,
    componentKey: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client
      .post<ApiExamResult>(`/api/exam-results/${resultId}/disclosures`, {
        version,
        component_key: componentKey,
        ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
      })
      .pipe(map(fromApiResult));
  }

  determineComponent(command: DetermineComponent) {
    return this.client
      .post<ApiExamResult>(`/api/exam-results/${command.resultId}/committee-assessments`, {
        version: command.version,
        component_key: command.componentKey,
        points: command.points,
        rationale: command.rationale.trim() || null,
        participant_member_ids: command.participants,
        vote: command.vote,
        dissent: command.dissent.map(({ memberId, statement }) => ({
          member_id: memberId,
          statement,
        })),
        ...(command.dayRevisions ? { day_revisions: command.dayRevisions } : {}),
      })
      .pipe(map(fromApiResult));
  }

  recordExternalResult(command: RecordExternalResult) {
    return this.client
      .post<ApiExamResult>(`/api/exam-results/${command.resultId}/external-results`, {
        version: command.version,
        area_key: command.areaKey,
        points: command.points,
        ...(command.grade ? { grade: command.grade } : {}),
        professional_status: command.professionalStatus,
        determining_authority: command.determiningAuthority,
        source_reference: command.sourceReference,
        ...(command.correctionReason ? { correction_reason: command.correctionReason } : {}),
        ...(command.dayRevisions ? { day_revisions: command.dayRevisions } : {}),
      })
      .pipe(map(fromApiResult));
  }

  confirmExternalResult(
    resultId: number,
    version: number,
    externalResultId: number,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client
      .post<ApiExamResult>(
        `/api/exam-results/${resultId}/external-results/${externalResultId}/confirm`,
        { version, ...(dayRevisions ? { day_revisions: dayRevisions } : {}) },
      )
      .pipe(map(fromApiResult));
  }

  determineExamResult(command: DetermineExamResult) {
    return this.client
      .post<ApiExamResult>(`/api/exam-results/${command.resultId}/determine`, {
        version: command.version,
        participant_member_ids: command.participants,
        vote: command.vote,
        dissent: command.dissent.map(({ memberId, statement }) => ({
          member_id: memberId,
          statement,
        })),
        ...(command.dayRevisions ? { day_revisions: command.dayRevisions } : {}),
      })
      .pipe(map(fromApiResult));
  }

  confirmResultRecord(resultId: number, version: number, dayRevisions?: Record<string, number>) {
    return this.client
      .post<ApiExamResult>(`/api/exam-results/${resultId}/record-confirmations`, {
        version,
        ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
      })
      .pipe(map(fromApiResult));
  }

  openResultCorrection(
    resultId: number,
    version: number,
    reason: string,
    reopeningReference?: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client
      .post<ApiExamResult>(`/api/exam-results/${resultId}/corrections`, {
        version,
        reason: reason.trim(),
        ...(reopeningReference?.trim() ? { reopening_reference: reopeningReference.trim() } : {}),
        ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
      })
      .pipe(map(fromApiResult));
  }

  communicateExamResult(
    resultId: number,
    version: number,
    method: string,
    communicatedAt: string,
    externalDocumentReference?: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client
      .post<ApiExamResult>(`/api/exam-results/${resultId}/communications`, {
        version,
        method: method.trim(),
        communicated_at: new Date(communicatedAt).toISOString(),
        ...(externalDocumentReference?.trim()
          ? {
              external_document_status: 'extern dokumentiert',
              external_document_reference: externalDocumentReference.trim(),
            }
          : {}),
        ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
      })
      .pipe(map(fromApiResult));
  }

  setExamResultRetention(command: SetResultRetention) {
    return this.client
      .put<ApiExamResult>(`/api/exam-results/${command.resultId}/retention`, {
        version: command.version,
        ...(command.periodStart ? { period_start: command.periodStart } : {}),
        ...(command.retainUntil ? { retain_until: command.retainUntil } : {}),
        legal_hold: command.legalHold,
        ...(command.holdReason ? { hold_reason: command.holdReason } : {}),
        ...(command.releaseReason ? { release_reason: command.releaseReason } : {}),
        ...(command.dayRevisions ? { day_revisions: command.dayRevisions } : {}),
      })
      .pipe(map(fromApiResult));
  }
}

function fromApiResult(value: ApiExamResult): ExamResult {
  const candidate = object(value.candidate, 'candidate');
  const model = object(value.model_version, 'model_version');
  const rules = object(model['rules'], 'model_version.rules');
  const passing = object(rules['passing'], 'model_version.rules.passing');
  const rounding = object(rules['rounding'], 'model_version.rules.rounding');
  const intermediate = object(rounding['intermediate'], 'rounding.intermediate');
  const overall = object(rounding['overall'], 'rounding.overall');
  const calculation = value.current_calculation
    ? object(value.current_calculation, 'current_calculation')
    : null;
  const calculationPath = calculation ? object(calculation['path'], 'calculation.path') : null;
  const retention = value.retention ? object(value.retention, 'retention') : null;
  return {
    id: value.id,
    roundCandidateId: value.round_candidate_id,
    dayRevisions: numberRecord(value.day_revisions, 'day_revisions'),
    version: value.version,
    state: value.state,
    correctionOpen: value.correction_open,
    legacyStatus: value.legacy_status,
    candidate: {
      id: number(candidate, 'id'),
      firstName: string(candidate, 'first_name'),
      lastName: string(candidate, 'last_name'),
      ihkExamNumber: nullableString(candidate, 'ihk_exam_number'),
      specialization: nullableString(candidate, 'specialization'),
    },
    modelVersion: {
      id: number(model, 'id'),
      modelKey: string(model, 'model_key'),
      version: number(model, 'version'),
      ihk: string(model, 'ihk'),
      occupation: string(model, 'occupation'),
      specialization: nullableString(model, 'specialization'),
      validFrom: string(model, 'valid_from'),
      validUntil: nullableString(model, 'valid_until'),
      rules: {
        components: arrayOfRecords(rules['components'], 'components').map((component) => ({
          key: string(component, 'key'),
          label: string(component, 'label'),
          mode: oneOf(component, 'mode', ['committee', 'independent']),
          weight: string(component, 'weight'),
          dayScoped: boolean(component, 'day_scoped'),
          requiredAssessors: number(component, 'required_assessors'),
          maxDeviation: string(component, 'max_deviation'),
          additionalAssessorOnDeviation: boolean(component, 'additional_assessor_on_deviation'),
          criteria: arrayOfRecords(component['criteria'], 'criteria').map((criterion) => ({
            key: string(criterion, 'key'),
            label: string(criterion, 'label'),
            rawMin: string(criterion, 'raw_min'),
            rawMax: string(criterion, 'raw_max'),
            weight: string(criterion, 'weight'),
          })),
        })),
        externalAreas: arrayOfRecords(rules['external_areas'], 'external_areas').map((area) => ({
          key: string(area, 'key'),
          label: string(area, 'label'),
          weight: string(area, 'weight'),
          required: boolean(area, 'required'),
        })),
        rounding: {
          intermediate: {
            mode: oneOf(intermediate, 'mode', ['none', 'half_up']),
            digits: nullableNumber(intermediate, 'digits'),
          },
          overall: {
            mode: oneOf(overall, 'mode', ['none', 'half_up']),
            digits: nullableNumber(overall, 'digits'),
          },
          thresholdBasis: oneOf(rounding, 'threshold_basis', ['unrounded', 'rounded']),
        },
        grades: arrayOfRecords(rules['grades'], 'grades').map((grade) => ({
          label: string(grade, 'label'),
          minPoints: string(grade, 'min_points'),
        })),
        passing: {
          overallMin: string(passing, 'overall_min'),
          componentMinima: stringRecord(passing['component_minima'], 'component_minima'),
          externalMinima: stringRecord(passing['external_minima'], 'external_minima'),
        },
        quorum: {
          minimumMembers: number(object(rules['quorum'], 'quorum'), 'minimum_members'),
          majority: oneOf(object(rules['quorum'], 'quorum'), 'majority', ['simple']),
        },
      },
      retentionRuleReference: string(model, 'retention_rule_reference'),
      retentionYears: number(model, 'retention_years'),
    },
    participants: numberArray(value.participants, 'participants'),
    disclosures: arrayOfRecords(value.disclosures, 'disclosures').map((item) => ({
      componentKey: string(item, 'component_key'),
      disclosedByMemberId: number(item, 'disclosed_by_member_id'),
      disclosedAt: string(item, 'disclosed_at'),
    })),
    individualAssessments: arrayOfRecords(
      value.individual_assessments,
      'individual_assessments',
    ).map((item) => ({
      id: number(item, 'id'),
      componentKey: string(item, 'component_key'),
      criterionKey: string(item, 'criterion_key'),
      assessorMemberId: number(item, 'assessor_member_id'),
      revision: number(item, 'revision'),
      rawPoints: decimalString(item, 'raw_points'),
      normalizedPoints: decimalString(item, 'normalized_points'),
      rationale: nullableString(item, 'rationale'),
      status: oneOf(item, 'status', ['draft', 'submitted', 'withdrawn', 'superseded']),
      changeReason: nullableString(item, 'change_reason'),
      submittedAt: nullableString(item, 'submitted_at'),
    })),
    individualAssessmentCounts: arrayOfRecords(
      value.individual_assessment_counts,
      'individual_assessment_counts',
    ).map((item) => ({
      componentKey: string(item, 'component_key'),
      draft: number(item, 'draft'),
      submitted: number(item, 'submitted'),
    })),
    committeeAssessments: arrayOfRecords(value.committee_assessments, 'committee_assessments').map(
      (item) => ({
        id: number(item, 'id'),
        componentKey: string(item, 'component_key'),
        revision: number(item, 'revision'),
        points: decimalString(item, 'points'),
        rationale: nullableString(item, 'rationale'),
        participantMemberIds: numberArray(item['participant_member_ids'], 'participant_member_ids'),
        vote: vote(item['vote']),
        dissent: dissent(item['dissent']),
        status: oneOf(item, 'status', ['current', 'superseded']),
        determinedAt: string(item, 'determined_at'),
      }),
    ),
    externalResults: arrayOfRecords(value.external_results, 'external_results').map((item) => ({
      id: number(item, 'id'),
      areaKey: string(item, 'area_key'),
      revision: number(item, 'revision'),
      points: string(item, 'points'),
      grade: nullableString(item, 'grade'),
      professionalStatus: string(item, 'professional_status'),
      determiningAuthority: string(item, 'determining_authority'),
      sourceReference: string(item, 'source_reference'),
      status: oneOf(item, 'status', ['unconfirmed', 'confirmed', 'replaced']),
      recordedByMemberId: number(item, 'recorded_by_member_id'),
      confirmedByMemberId: nullableNumber(item, 'confirmed_by_member_id'),
      correctionReason: nullableString(item, 'correction_reason'),
    })),
    currentCalculation: calculation
      ? {
          id: number(calculation, 'id'),
          version: number(calculation, 'version'),
          totalPoints: string(calculation, 'total_points'),
          grade: string(calculation, 'grade'),
          passed: boolean(calculation, 'passed'),
          path: {
            inputs: arrayOfRecords(calculationPath?.['inputs'], 'calculation.path.inputs').map(
              (item) => ({
                kind: string(item, 'kind'),
                key: string(item, 'key'),
                points: string(item, 'points'),
                weight: string(item, 'weight'),
              }),
            ),
            unroundedTotal: string(calculationPath, 'unrounded_total'),
            roundedTotal: string(calculationPath, 'rounded_total'),
            thresholdBasis: string(calculationPath, 'threshold_basis'),
          },
        }
      : null,
    determinations: arrayOfRecords(value.determinations, 'determinations').map((item) => ({
      id: number(item, 'id'),
      revision: number(item, 'revision'),
      participantMemberIds: numberArray(item['participant_member_ids'], 'participant_member_ids'),
      vote: vote(item['vote']),
      dissent: dissent(item['dissent']),
      status: oneOf(item, 'status', ['current', 'superseded']),
      determinedAt: string(item, 'determined_at'),
      confirmationMemberIds: numberArray(
        item['confirmation_member_ids'],
        'confirmation_member_ids',
      ),
    })),
    currentDetermination: value.current_determination
      ? determination(object(value.current_determination, 'current_determination'))
      : null,
    corrections: arrayOfRecords(value.corrections, 'corrections').map((item) => ({
      id: number(item, 'id'),
      reason: string(item, 'reason'),
      status: oneOf(item, 'status', ['open', 'completed']),
      reopeningReference: nullableString(item, 'reopening_reference'),
    })),
    communications: arrayOfRecords(value.communications, 'communications').map((item) => ({
      id: number(item, 'id'),
      method: string(item, 'method'),
      communicatedAt: string(item, 'communicated_at'),
      externalDocumentStatus: nullableString(item, 'external_document_status'),
      externalDocumentReference: nullableString(item, 'external_document_reference'),
      status: oneOf(item, 'status', ['current', 'obsolete']),
    })),
    retention: retention
      ? {
          ruleReference: string(retention, 'rule_reference'),
          periodStart: nullableString(retention, 'period_start'),
          retainUntil: nullableString(retention, 'retain_until'),
          legalHold: boolean(retention, 'legal_hold'),
          holdReason: nullableString(retention, 'hold_reason'),
        }
      : null,
    exports: arrayOfRecords(value.exports, 'exports').map((item) => ({
      id: number(item, 'id'),
      resultDeterminationId: nullableNumber(item, 'result_determination_id'),
      exportKind: oneOf(item, 'export_kind', ['machine', 'human']),
      status: oneOf(item, 'status', ['draft', 'determined', 'superseded']),
      generatedAt: string(item, 'generated_at'),
    })),
    permissions: {
      assessOwn: boolean(value.permissions, 'assess_own'),
      disclose: boolean(value.permissions, 'disclose'),
      determineComponent: boolean(value.permissions, 'determine_component'),
      manageExternal: boolean(value.permissions, 'manage_external'),
      determineResult: boolean(value.permissions, 'determine_result'),
      confirmRecord: boolean(value.permissions, 'confirm_record'),
      coordinateCorrection: boolean(value.permissions, 'coordinate_correction'),
      communicate: boolean(value.permissions, 'communicate'),
      manageRetention: boolean(value.permissions, 'manage_retention'),
    },
    exportAvailability: {
      machine: linkHref(value._links['machine_export']) !== null,
      human: linkHref(value._links['human_export']) !== null,
    },
  } satisfies ExamResult;
}

function object(value: unknown, label: string): Record<string, unknown> {
  if (!isRecord(value)) throw new Error(`Expected ${label} to be an object`);
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function linkHref(value: unknown): string | null {
  if (typeof value !== 'object' || value === null || !('href' in value)) return null;
  return typeof value.href === 'string' ? value.href : null;
}

function required(value: Record<string, unknown> | null, key: string): unknown {
  if (!value || !(key in value)) throw new Error(`Missing required result field: ${key}`);
  return value[key];
}

function string(value: Record<string, unknown> | null, key: string): string {
  const field = required(value, key);
  if (typeof field !== 'string') throw new Error(`Expected result field ${key} to be a string`);
  return field;
}

function decimalString(value: Record<string, unknown>, key: string): string {
  const field = required(value, key);
  if (typeof field !== 'string' && typeof field !== 'number') {
    throw new Error(`Expected result field ${key} to be a decimal string or number`);
  }
  return String(field);
}

function nullableString(value: Record<string, unknown> | null, key: string): string | null {
  const field = required(value, key);
  if (field !== null && typeof field !== 'string') {
    throw new Error(`Expected result field ${key} to be a string or null`);
  }
  return field;
}

function number(value: Record<string, unknown> | null, key: string): number {
  const field = required(value, key);
  if (typeof field !== 'number') throw new Error(`Expected result field ${key} to be a number`);
  return field;
}

function nullableNumber(value: Record<string, unknown>, key: string): number | null {
  const field = required(value, key);
  if (field !== null && typeof field !== 'number') {
    throw new Error(`Expected result field ${key} to be a number or null`);
  }
  return field;
}

function boolean(value: Record<string, unknown>, key: string): boolean {
  const field = required(value, key);
  if (typeof field !== 'boolean') throw new Error(`Expected result field ${key} to be a boolean`);
  return field;
}

function arrayOfRecords(value: unknown, label: string): Record<string, unknown>[] {
  if (!Array.isArray(value)) throw new Error(`Expected ${label} to be an array`);
  return value.map((item) => object(item, label));
}

function numberArray(value: unknown, label: string): number[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'number')) {
    throw new Error(`Expected ${label} to be an array of numbers`);
  }
  return value;
}

function stringRecord(value: unknown, label: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [key, item] of Object.entries(object(value, label))) {
    if (typeof item !== 'string') throw new Error(`Expected ${label} to contain only strings`);
    result[key] = item;
  }
  return result;
}

function numberRecord(value: unknown, label: string): Record<string, number> {
  const result: Record<string, number> = {};
  for (const [key, item] of Object.entries(object(value, label))) {
    if (typeof item !== 'number') throw new Error(`Expected ${label} to contain only numbers`);
    result[key] = item;
  }
  return result;
}

function oneOf<const Value extends string>(
  value: Record<string, unknown>,
  key: string,
  allowed: readonly Value[],
): Value {
  const field = string(value, key);
  const match = allowed.find((candidate) => candidate === field);
  if (match === undefined) throw new Error(`Unexpected result field ${key}: ${field}`);
  return match;
}

function vote(value: unknown) {
  const valueObject = object(value, 'vote');
  return {
    yes: numberArray(valueObject['yes'], 'vote.yes'),
    no: numberArray(valueObject['no'], 'vote.no'),
    abstain: numberArray(valueObject['abstain'], 'vote.abstain'),
  };
}

function dissent(value: unknown) {
  return arrayOfRecords(value, 'dissent').map((item) => ({
    memberId: number(item, 'member_id'),
    statement: string(item, 'statement'),
  }));
}

function determination(value: Record<string, unknown>) {
  return {
    id: number(value, 'id'),
    revision: number(value, 'revision'),
    participantMemberIds: numberArray(value['participant_member_ids'], 'participant_member_ids'),
    vote: vote(value['vote']),
    dissent: dissent(value['dissent']),
    status: oneOf(value, 'status', ['current', 'superseded']),
    determinedAt: string(value, 'determined_at'),
    confirmationMemberIds: numberArray(value['confirmation_member_ids'], 'confirmation_member_ids'),
  };
}
