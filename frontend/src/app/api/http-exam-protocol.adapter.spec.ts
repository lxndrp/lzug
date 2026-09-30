import { HttpHeaders, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import type { ExamProtocol as ApiExamProtocol } from './execution.models';
import { HttpExamProtocolAdapter } from './http-exam-protocol.adapter';

describe('HttpExamProtocolAdapter', () => {
  let adapter: HttpExamProtocolAdapter;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), HttpExamProtocolAdapter],
    });
    adapter = TestBed.inject(HttpExamProtocolAdapter);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('maps protocol records and workflow permissions into the feature model', () => {
    let result: unknown;
    adapter.get(7, 11).subscribe((protocol) => (result = protocol));
    const request = http.expectOne('/api/confirmed-plan-days/7/slots/11/protocol');
    expect(request.request.method).toBe('GET');
    request.flush(
      apiProtocol({
        day_revision: 4,
        current_revision: apiRevision({
          declaration: 'with_special_occurrences',
          workflow_state: 'submitted',
          entries: [
            {
              id: 72,
              category: 'interruption',
              statement: 'Die Prüfung wurde kurz unterbrochen.',
              occurred_from: '2026-11-16T09:20:00+01:00',
              occurred_to: null,
              recorded_by_member_id: 1,
              created_at: '2026-11-16T09:25:00+01:00',
            },
          ],
          responses: [
            {
              id: 8,
              committee_member_id: 3,
              response: 'reservation',
              entry_id: 72,
              statement: 'Zeitangabe prüfen',
              responded_at: '2026-11-16T10:01:00+01:00',
            },
          ],
        }),
        correction_requests: [
          {
            id: 9,
            version: 1,
            requested_by_member_id: 3,
            reason: 'Zeitangabe prüfen',
            status: 'pending',
            reopening_reference: null,
          },
        ],
      }),
    );
    expect(result).toEqual({
      id: 41,
      examSlotId: 11,
      dayRevision: 4,
      currentVersion: 1,
      state: 'in_progress',
      closingReady: false,
      currentRevision: {
        id: 71,
        version: 1,
        declaration: 'with_special_occurrences',
        workflowState: 'submitted',
        changeReason: null,
        submittedAt: null,
        obsolete: false,
        missingResponseMemberIds: [1, 3],
        entries: [
          {
            id: 72,
            category: 'interruption',
            statement: 'Die Prüfung wurde kurz unterbrochen.',
            occurredFrom: '2026-11-16T09:20:00+01:00',
            occurredTo: null,
            recordedByMemberId: 1,
            createdAt: '2026-11-16T09:25:00+01:00',
          },
        ],
        responses: [
          {
            id: 8,
            committeeMemberId: 3,
            response: 'reservation',
            entryId: 72,
            statement: 'Zeitangabe prüfen',
            respondedAt: '2026-11-16T10:01:00+01:00',
          },
        ],
      },
      history: [expect.objectContaining({ version: 1 })],
      correctionRequests: [
        {
          id: 9,
          version: 1,
          requestedByMemberId: 3,
          reason: 'Zeitangabe prüfen',
          status: 'pending',
          reopeningReference: null,
        },
      ],
      permissions: {
        edit: true,
        submit: true,
        respond: true,
        requestCorrection: true,
        coordinateCorrection: false,
        manageRetention: false,
      },
      exports: { machineReadable: true, humanReadable: true },
    });
  });

  it('maps every protocol write operation to its existing API path and payload', () => {
    adapter
      .update({
        protocolId: 41,
        version: 2,
        declaration: 'with_special_occurrences',
        entries: [
          {
            category: 'interruption',
            statement: 'Zwei Minuten unterbrochen.',
            occurredFrom: '2026-11-16T09:20:00.000Z',
            occurredTo: '2026-11-16T09:22:00.000Z',
          },
        ],
        changeReason: '  Sachverhalt ergänzt  ',
        dayRevision: 5,
      })
      .subscribe();
    const update = http.expectOne('/api/exam-protocols/41');
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual({
      version: 2,
      declaration: 'with_special_occurrences',
      entries: [
        {
          category: 'interruption',
          statement: 'Zwei Minuten unterbrochen.',
          occurred_from: '2026-11-16T09:20:00.000Z',
          occurred_to: '2026-11-16T09:22:00.000Z',
        },
      ],
      change_reason: 'Sachverhalt ergänzt',
      day_revision: 5,
    });
    update.flush(apiProtocol());

    adapter.submit(41, 3, 5).subscribe();
    const submit = http.expectOne('/api/exam-protocols/41/submit');
    expect(submit.request.method).toBe('POST');
    expect(submit.request.body).toEqual({ version: 3, day_revision: 5 });
    submit.flush(apiProtocol());

    adapter.respond(41, 3, 'reservation', 72, '  Zeitangabe prüfen  ', 5).subscribe();
    const response = http.expectOne('/api/exam-protocols/41/responses');
    expect(response.request.method).toBe('POST');
    expect(response.request.body).toEqual({
      version: 3,
      response: 'reservation',
      entry_id: 72,
      statement: 'Zeitangabe prüfen',
      day_revision: 5,
    });
    response.flush(apiProtocol());

    adapter.requestCorrection(41, 3, '  Eintrag ergänzen  ', 5).subscribe();
    const correction = http.expectOne('/api/exam-protocols/41/correction-requests');
    expect(correction.request.method).toBe('POST');
    expect(correction.request.body).toEqual({
      version: 3,
      reason: 'Eintrag ergänzen',
      day_revision: 5,
    });
    correction.flush(apiProtocol());

    adapter.openCorrection(41, 3, 9, '  Korrektur koordinieren  ', '  REOPEN-36  ', 5).subscribe();
    const openCorrection = http.expectOne('/api/exam-protocols/41/open-correction');
    expect(openCorrection.request.method).toBe('POST');
    expect(openCorrection.request.body).toEqual({
      version: 3,
      correction_request_id: 9,
      reason: 'Korrektur koordinieren',
      reopening_reference: 'REOPEN-36',
      day_revision: 5,
    });
    openCorrection.flush(apiProtocol());
  });

  it('downloads machine and human exports with response metadata', () => {
    let machine: unknown;
    adapter.export(41, 'machine-readable').subscribe((value) => (machine = value));
    const json = http.expectOne('/api/exam-protocols/41/export.json');
    expect(json.request.method).toBe('GET');
    expect(json.request.responseType).toBe('text');
    json.flush('{"version":1}', {
      headers: new HttpHeaders({
        'content-type': 'application/json',
        'content-disposition': 'attachment; filename="protocol-41.json"',
      }),
    });
    expect(machine).toEqual({
      content: '{"version":1}',
      mediaType: 'application/json',
      fileName: 'protocol-41.json',
    });

    let human: unknown;
    adapter.export(41, 'human-readable').subscribe((value) => (human = value));
    const text = http.expectOne('/api/exam-protocols/41/export.txt');
    text.flush('Prüfungsprotokoll', { headers: { 'content-type': 'text/plain; charset=utf-8' } });
    expect(human).toEqual({
      content: 'Prüfungsprotokoll',
      mediaType: 'text/plain; charset=utf-8',
      fileName: 'pruefungsprotokoll-41.txt',
    });
  });
});

function apiRevision(overrides: Partial<ApiExamProtocol['current_revision']> = {}) {
  return {
    id: 71,
    version: 1,
    declaration: null,
    workflow_state: 'draft',
    change_reason: null,
    submitted_at: null,
    obsolete: false,
    missing_response_member_ids: [1, 3],
    entries: [],
    responses: [],
    ...overrides,
  } as ApiExamProtocol['current_revision'];
}

function apiProtocol(overrides: Partial<ApiExamProtocol> = {}): ApiExamProtocol {
  const currentRevision = overrides.current_revision ?? apiRevision();
  return {
    id: 41,
    exam_slot_id: 11,
    current_version: 1,
    state: 'in_progress',
    closing_ready: false,
    current_revision: currentRevision,
    history: overrides.history ?? [currentRevision],
    correction_requests: [],
    permissions: {
      edit: true,
      submit: true,
      respond: true,
      request_correction: true,
      coordinate_correction: false,
      manage_retention: false,
    },
    _links: {
      self: { href: '/api/exam-protocols/41' },
      machine_export: { href: '/api/exam-protocols/41/export.json' },
      human_export: { href: '/api/exam-protocols/41/export.txt' },
    },
    ...overrides,
  };
}
