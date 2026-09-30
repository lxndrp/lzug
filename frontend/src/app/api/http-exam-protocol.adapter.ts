import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { catchError, map, throwError } from 'rxjs';

import type {
  ExamProtocol as ApiExamProtocol,
  ExamProtocolDeclaration as ApiProtocolDeclaration,
  ExamProtocolEntryCategory as ApiProtocolEntryCategory,
} from './execution.models';
import type { DomainResourceWrite, ExamProtocolContentRequest } from './generated/types.gen';
import { ApiClient } from './api-client.service';
import { toApplicationError } from './application-error';
import type {
  ExamProtocol,
  ProtocolExport,
  ProtocolExportFormat,
  UpdateExamProtocol,
} from '../exam-protocol/exam-protocol.models';
import type { ExamProtocolPort } from '../exam-protocol/exam-protocol.port';

/** HTTP/OpenAPI adapter for the transport-neutral exam-protocol feature port. */
@Injectable({ providedIn: 'root' })
export class HttpExamProtocolAdapter implements ExamProtocolPort {
  private readonly client = inject(ApiClient);
  private readonly http = inject(HttpClient);

  get(dayId: number, slotId: number) {
    return this.client
      .get<ApiExamProtocol>(`/api/confirmed-plan-days/${dayId}/slots/${slotId}/protocol`)
      .pipe(map(fromApiProtocol));
  }

  update(command: UpdateExamProtocol) {
    const body: ExamProtocolContentRequest & { day_revision?: number } = {
      version: command.version,
      declaration: command.declaration,
      entries: command.entries.map((entry) => ({
        category: entry.category as ApiProtocolEntryCategory,
        statement: entry.statement,
        occurred_from: entry.occurredFrom,
        occurred_to: entry.occurredTo,
      })),
      ...(command.changeReason?.trim() ? { change_reason: command.changeReason.trim() } : {}),
      ...(command.dayRevision ? { day_revision: command.dayRevision } : {}),
    };
    return this.client
      .patch<ApiExamProtocol>(`/api/exam-protocols/${command.protocolId}`, body)
      .pipe(map(fromApiProtocol));
  }

  submit(protocolId: number, version: number, dayRevision?: number) {
    const body: DomainResourceWrite = {
      version,
      ...(dayRevision ? { day_revision: dayRevision } : {}),
    };
    return this.client
      .post<ApiExamProtocol>(`/api/exam-protocols/${protocolId}/submit`, body)
      .pipe(map(fromApiProtocol));
  }

  respond(
    protocolId: number,
    version: number,
    response: 'confirmed' | 'reservation',
    entryId?: number,
    statement?: string,
    dayRevision?: number,
  ) {
    const body: DomainResourceWrite = {
      version,
      response,
      ...(entryId === undefined ? {} : { entry_id: entryId }),
      ...(statement?.trim() ? { statement: statement.trim() } : {}),
      ...(dayRevision ? { day_revision: dayRevision } : {}),
    };
    return this.client
      .post<ApiExamProtocol>(`/api/exam-protocols/${protocolId}/responses`, body)
      .pipe(map(fromApiProtocol));
  }

  requestCorrection(protocolId: number, version: number, reason: string, dayRevision?: number) {
    const body: DomainResourceWrite = {
      version,
      reason: reason.trim(),
      ...(dayRevision ? { day_revision: dayRevision } : {}),
    };
    return this.client
      .post<ApiExamProtocol>(`/api/exam-protocols/${protocolId}/correction-requests`, body)
      .pipe(map(fromApiProtocol));
  }

  openCorrection(
    protocolId: number,
    version: number,
    correctionRequestId: number,
    reason: string,
    reopeningReference?: string,
    dayRevision?: number,
  ) {
    const body: DomainResourceWrite = {
      version,
      correction_request_id: correctionRequestId,
      reason: reason.trim(),
      ...(reopeningReference?.trim() ? { reopening_reference: reopeningReference.trim() } : {}),
      ...(dayRevision ? { day_revision: dayRevision } : {}),
    };
    return this.client
      .post<ApiExamProtocol>(`/api/exam-protocols/${protocolId}/open-correction`, body)
      .pipe(map(fromApiProtocol));
  }

  export(protocolId: number, format: ProtocolExportFormat) {
    const extension = format === 'machine-readable' ? 'json' : 'txt';
    return this.http
      .get(`/api/exam-protocols/${protocolId}/export.${extension}`, {
        observe: 'response',
        responseType: 'text',
      })
      .pipe(
        map((response): ProtocolExport => ({
          content: response.body ?? '',
          mediaType:
            response.headers.get('content-type') ??
            (format === 'machine-readable'
              ? 'application/json; charset=utf-8'
              : 'text/plain; charset=utf-8'),
          fileName:
            response.headers.get('content-disposition')?.match(/filename="?([^";]+)"?/i)?.[1] ??
            `pruefungsprotokoll-${protocolId}.${extension}`,
        })),
        catchError((error: unknown) => throwError(() => toApplicationError(error))),
      );
  }
}

function fromApiProtocol(value: ApiExamProtocol): ExamProtocol {
  return {
    id: value.id,
    examSlotId: value.exam_slot_id,
    ...(value.day_revision === undefined ? {} : { dayRevision: value.day_revision }),
    currentVersion: value.current_version,
    state: value.state,
    closingReady: value.closing_ready,
    currentRevision: fromApiRevision(value.current_revision),
    history: value.history.map(fromApiRevision),
    correctionRequests: value.correction_requests.map((request) => ({
      id: request.id,
      version: request.version,
      requestedByMemberId: request.requested_by_member_id,
      reason: request.reason,
      status: request.status,
      reopeningReference: request.reopening_reference,
    })),
    permissions: {
      edit: value.permissions.edit,
      submit: value.permissions.submit,
      respond: value.permissions.respond,
      requestCorrection: value.permissions.request_correction,
      coordinateCorrection: value.permissions.coordinate_correction,
      manageRetention: value.permissions.manage_retention,
    },
    exports: {
      machineReadable: Boolean(value._links['machine_export']?.href),
      humanReadable: Boolean(value._links['human_export']?.href),
    },
  };
}

function fromApiRevision(
  value: ApiExamProtocol['current_revision'],
): ExamProtocol['currentRevision'] {
  return {
    id: value.id,
    version: value.version,
    declaration: value.declaration as ApiProtocolDeclaration | null,
    workflowState: value.workflow_state,
    changeReason: value.change_reason,
    submittedAt: value.submitted_at,
    obsolete: value.obsolete,
    missingResponseMemberIds: [...value.missing_response_member_ids],
    entries: value.entries.map((entry) => ({
      id: entry.id,
      category: entry.category as ApiProtocolEntryCategory,
      statement: entry.statement,
      occurredFrom: entry.occurred_from,
      occurredTo: entry.occurred_to,
      recordedByMemberId: entry.recorded_by_member_id,
      createdAt: entry.created_at,
    })),
    responses: value.responses.map((response) => ({
      id: response.id,
      committeeMemberId: response.committee_member_id,
      response: response.response,
      entryId: response.entry_id,
      statement: response.statement,
      respondedAt: response.responded_at,
    })),
  };
}
