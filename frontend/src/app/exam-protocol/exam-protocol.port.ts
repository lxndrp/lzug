import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import type {
  ExamProtocol,
  ProtocolExport,
  ProtocolExportFormat,
  UpdateExamProtocol,
} from './exam-protocol.models';

/** Protocol reads and revision/workflow commands required by the feature. */
export interface ExamProtocolPort {
  get(dayId: number, slotId: number): Observable<ExamProtocol>;
  update(command: UpdateExamProtocol): Observable<ExamProtocol>;
  submit(protocolId: number, version: number, dayRevision?: number): Observable<ExamProtocol>;
  respond(
    protocolId: number,
    version: number,
    response: 'confirmed' | 'reservation',
    entryId?: number,
    statement?: string,
    dayRevision?: number,
  ): Observable<ExamProtocol>;
  requestCorrection(
    protocolId: number,
    version: number,
    reason: string,
    dayRevision?: number,
  ): Observable<ExamProtocol>;
  openCorrection(
    protocolId: number,
    version: number,
    correctionRequestId: number,
    reason: string,
    reopeningReference?: string,
    dayRevision?: number,
  ): Observable<ExamProtocol>;
  export(protocolId: number, format: ProtocolExportFormat): Observable<ProtocolExport>;
}

export const EXAM_PROTOCOL_PORT = new InjectionToken<ExamProtocolPort>('EXAM_PROTOCOL_PORT');
