import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import { ExamRoundApiService } from './exam-round-api.service';
import type {
  ExamHalfYear as ApiExamHalfYear,
  ExamRound as ApiExamRound,
  ExamRoundLifecycle as ApiRoundLifecycle,
  ExamRoundCreate,
} from './planning.models';
import type {
  CreateExamRound,
  ExamHalfYear,
  ExamRound,
  LifecycleExportFormat,
  RoundCandidateTerminalStatus,
  RoundLifecycle,
  RoundReopening,
} from '../exam-half-years/exam-half-years.models';
import type { ExamHalfYearsPort } from '../exam-half-years/exam-half-years.port';

/** HTTP adapter for the transport-neutral examination-context feature contract. */
@Injectable({ providedIn: 'root' })
export class HttpExamHalfYearsAdapter implements ExamHalfYearsPort {
  private readonly api = inject(ExamRoundApiService);
  private readonly http = inject(HttpClient);

  listHalfYears() {
    return this.api.listExamHalfYears().pipe(map((items) => items.map(toHalfYear)));
  }

  listRounds() {
    return this.api.listExamRounds().pipe(map((items) => items.map(toRound)));
  }

  createRound(payload: CreateExamRound) {
    const apiPayload: ExamRoundCreate = {
      ...('halfYearId' in payload && payload.halfYearId !== undefined
        ? { exam_half_year_id: payload.halfYearId }
        : { season: payload.season, year: payload.year }),
      committee_id: payload.committeeId,
      name: payload.name,
    };
    return this.api.createExamRound(apiPayload).pipe(map(toRound));
  }

  getRoundLifecycle(roundId: number) {
    return this.api.getExamRoundLifecycle(roundId).pipe(map(toLifecycle));
  }

  closeRound(roundId: number, revision: number) {
    return this.api.closeExamRound(roundId, revision).pipe(map(toLifecycle));
  }

  cancelRound(roundId: number, revision: number, reason: string) {
    return this.api.cancelExamRound(roundId, revision, reason).pipe(map(toLifecycle));
  }

  reopenRound(roundId: number, payload: RoundReopening) {
    return this.api
      .reopenExamRound(roundId, {
        ...payload,
        scope: payload.scope.map(({ kind, entityId }) => ({ kind, entity_id: entityId })),
      })
      .pipe(map(toLifecycle));
  }

  deleteEmptyRound(roundId: number) {
    return this.api.deleteEmptyExamRound(roundId);
  }

  setCandidateTerminalStatus(
    roundId: number,
    roundCandidateId: number,
    payload: RoundCandidateTerminalStatus,
  ) {
    return this.api
      .setRoundCandidateTerminalStatus(roundId, roundCandidateId, {
        revision: payload.revision,
        terminal_status: payload.terminalStatus,
        ...(payload.reason !== undefined ? { reason: payload.reason } : {}),
        ...(payload.effectiveNewRoundId !== undefined
          ? { effective_new_round_id: payload.effectiveNewRoundId }
          : {}),
        ...(payload.postponedUntil !== undefined
          ? { postponed_until: payload.postponedUntil }
          : {}),
        ...(payload.ihkDecisionReference !== undefined
          ? { ihk_decision_reference: payload.ihkDecisionReference }
          : {}),
      })
      .pipe(map(toLifecycle));
  }

  documentIhkStatus(
    roundId: number,
    resultId: number,
    documentStatus: string,
    documentReference: string,
  ) {
    return this.api
      .documentExamRoundIhkStatus(roundId, resultId, documentStatus, documentReference)
      .pipe(map(toLifecycle));
  }

  exportLifecycle(roundId: number, format: LifecycleExportFormat) {
    return this.http
      .get(`/api/exam-rounds/${roundId}/lifecycle/export.${format === 'text' ? 'txt' : format}`, {
        observe: 'response',
        responseType: 'text',
      })
      .pipe(
        map((response) => ({
          content: response.body ?? '',
          mediaType:
            response.headers.get('content-type') ??
            (format === 'json' ? 'application/json; charset=utf-8' : 'text/plain; charset=utf-8'),
          fileName:
            response.headers.get('content-disposition')?.match(/filename="?([^";]+)"?/i)?.[1] ??
            `pruefungsrunde-${roundId}-nachweis.${format === 'text' ? 'txt' : 'json'}`,
        })),
      );
  }
}

function toHalfYear(value: ApiExamHalfYear): ExamHalfYear {
  return { id: value.id, season: value.season, year: value.year, status: value.status };
}

function toRound(value: ApiExamRound): ExamRound {
  return {
    id: value.id,
    halfYearId: value.exam_half_year_id,
    name: value.name,
    committeeId: value.committee_id,
    status: value.status,
  };
}

function toLifecycle(value: ApiRoundLifecycle): RoundLifecycle {
  return {
    roundId: value.round_id,
    revision: value.revision,
    status: value.status,
    historicalWithoutFormalEvidence: value.historical_without_formal_evidence,
    evaluation: {
      ready: value.evaluation.ready,
      items: value.evaluation.items.map(({ code, label, ok }) => ({ code, label, ok })),
    },
    candidates: value.candidates.map(({ round_candidate_id, candidate_id, terminal_status }) => ({
      roundCandidateId: round_candidate_id,
      candidateId: candidate_id,
      terminalStatus: terminal_status,
    })),
    retention: {
      retainUntil: value.retention.retain_until,
      legalHold: value.retention.legal_hold,
    },
    ihkStatuses: value.ihk_statuses.map(
      ({ id, exam_result_id, document_status, document_reference }) => ({
        id,
        examResultId: exam_result_id,
        documentStatus: document_status,
        documentReference: document_reference,
      }),
    ),
    permissions: {
      close: value.permissions.close,
      cancel: value.permissions.cancel,
      reopen: value.permissions.reopen,
      delete: value.permissions.delete,
    },
    history: value.history.map(({ id, round_revision, event_type, reason }) => ({
      id,
      roundRevision: round_revision,
      eventType: event_type,
      reason,
    })),
  };
}
