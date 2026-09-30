import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { HttpExamHalfYearsAdapter } from './http-exam-half-years.adapter';

describe('HttpExamHalfYearsAdapter', () => {
  let adapter: HttpExamHalfYearsAdapter;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [HttpExamHalfYearsAdapter, provideHttpClient(), provideHttpClientTesting()],
    });
    adapter = TestBed.inject(HttpExamHalfYearsAdapter);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('maps half-year and round collections into link-free feature models', () => {
    adapter.listHalfYears().subscribe((items) => {
      expect(items).toEqual([{ id: 2, season: 'winter', year: 2026, status: 'active' }]);
    });
    http.expectOne('/api/exam-half-years').flush({
      items: [
        {
          id: 2,
          season: 'winter',
          year: 2026,
          status: 'active',
          _links: { self: { href: '/api/exam-half-years/2' } },
        },
      ],
      _links: {},
    });

    adapter.listRounds().subscribe((items) => {
      expect(items).toEqual([
        {
          id: 4,
          halfYearId: 2,
          name: 'Winter 2026 · Ausschuss',
          committeeId: 3,
          status: 'draft',
        },
      ]);
    });
    http.expectOne('/api/exam-rounds').flush({
      items: [apiRound()],
      _links: {},
    });
  });

  it('maps both round-creation commands to the existing backend contract', () => {
    adapter
      .createRound({
        season: 'summer',
        year: 2027,
        committeeId: 3,
        name: 'Sommer 2027 · Ausschuss',
      })
      .subscribe((round) => expect(round.halfYearId).toBe(2));
    const createContext = http.expectOne('/api/exam-rounds');
    expect(createContext.request.method).toBe('POST');
    expect(createContext.request.body).toEqual({
      season: 'summer',
      year: 2027,
      committee_id: 3,
      name: 'Sommer 2027 · Ausschuss',
    });
    createContext.flush(apiRound());

    adapter
      .createRound({ halfYearId: 2, committeeId: 3, name: 'Winter 2026 · Ausschuss' })
      .subscribe((round) => expect(round.committeeId).toBe(3));
    const assignCommittee = http.expectOne('/api/exam-rounds');
    expect(assignCommittee.request.body).toEqual({
      exam_half_year_id: 2,
      committee_id: 3,
      name: 'Winter 2026 · Ausschuss',
    });
    assignCommittee.flush(apiRound());
  });

  it('maps lifecycle data and keeps export and status contracts free of HAL links', () => {
    adapter.getRoundLifecycle(4).subscribe((lifecycle) => {
      expect(lifecycle).toEqual({
        roundId: 4,
        revision: 2,
        status: 'closed',
        historicalWithoutFormalEvidence: false,
        evaluation: { ready: true, items: [{ code: 'closed', label: 'Abschluss', ok: true }] },
        candidates: [{ roundCandidateId: 8, candidateId: 12, terminalStatus: 'open' }],
        retention: { retainUntil: '2036-01-01', legalHold: true },
        ihkStatuses: [
          {
            id: 5,
            examResultId: 9,
            documentStatus: 'zugestellt',
            documentReference: 'IHK-2',
          },
        ],
        permissions: { close: false, cancel: false, reopen: true, delete: false },
        history: [{ id: 3, roundRevision: 2, eventType: 'closed', reason: 'abgeschlossen' }],
      });
    });
    http.expectOne('/api/exam-rounds/4/lifecycle').flush(apiLifecycle());
  });

  it('preserves lifecycle command routes and translates feature fields to API payloads', () => {
    adapter.closeRound(4, 3).subscribe();
    const close = http.expectOne('/api/exam-rounds/4/closure');
    expect(close.request.method).toBe('POST');
    expect(close.request.body).toEqual({ revision: 3, confirmed: true });
    close.flush(apiLifecycle());

    adapter.cancelRound(4, 3, 'Grund').subscribe();
    const cancel = http.expectOne('/api/exam-rounds/4/cancellation');
    expect(cancel.request.body).toEqual({ revision: 3, confirmed: true, reason: 'Grund' });
    cancel.flush(apiLifecycle());

    adapter
      .reopenRound(4, {
        revision: 4,
        occasion: 'Anlass',
        source: 'Quelle',
        reason: 'Grund',
        scope: [{ kind: 'planning', entityId: 8 }],
      })
      .subscribe();
    const reopen = http.expectOne('/api/exam-rounds/4/reopenings');
    expect(reopen.request.body).toEqual({
      revision: 4,
      occasion: 'Anlass',
      source: 'Quelle',
      reason: 'Grund',
      scope: [{ kind: 'planning', entity_id: 8 }],
    });
    reopen.flush(apiLifecycle());

    adapter
      .setCandidateTerminalStatus(4, 8, {
        revision: 4,
        terminalStatus: 'postponed',
        reason: 'Grund',
        postponedUntil: '2027-12-01',
      })
      .subscribe();
    const terminal = http.expectOne('/api/exam-rounds/4/candidates/8/terminal-status');
    expect(terminal.request.method).toBe('PUT');
    expect(terminal.request.body).toEqual({
      revision: 4,
      terminal_status: 'postponed',
      reason: 'Grund',
      postponed_until: '2027-12-01',
    });
    terminal.flush(apiLifecycle());

    adapter.documentIhkStatus(4, 9, 'zugestellt', 'IHK-2').subscribe();
    const ihk = http.expectOne('/api/exam-rounds/4/results/9/ihk-status');
    expect(ihk.request.method).toBe('PUT');
    expect(ihk.request.body).toEqual({
      document_status: 'zugestellt',
      document_reference: 'IHK-2',
    });
    ihk.flush(apiLifecycle());

    adapter.deleteEmptyRound(4).subscribe();
    const remove = http.expectOne('/api/exam-rounds/4');
    expect(remove.request.method).toBe('DELETE');
    remove.flush(null);
  });

  it('returns lifecycle exports with response metadata for the browser download', () => {
    adapter.exportLifecycle(4, 'json').subscribe((exported) => {
      expect(exported).toEqual({
        content: '{"status":"closed"}',
        mediaType: 'application/json',
        fileName: 'exam-round-4.json',
      });
    });
    const json = http.expectOne('/api/exam-rounds/4/lifecycle/export.json');
    expect(json.request.method).toBe('GET');
    expect(json.request.responseType).toBe('text');
    json.flush('{"status":"closed"}', {
      headers: {
        'content-type': 'application/json',
        'content-disposition': 'attachment; filename="exam-round-4.json"',
      },
    });

    adapter.exportLifecycle(4, 'text').subscribe((exported) => {
      expect(exported.fileName).toBe('pruefungsrunde-4-nachweis.txt');
      expect(exported.mediaType).toBe('text/plain; charset=utf-8');
      expect(exported.content).toContain('Prüfungsrundennachweis');
    });
    http.expectOne('/api/exam-rounds/4/lifecycle/export.text').flush('Prüfungsrundennachweis', {
      headers: { 'content-type': 'text/plain; charset=utf-8' },
    });
  });
});

function apiRound() {
  return {
    id: 4,
    exam_half_year_id: 2,
    name: 'Winter 2026 · Ausschuss',
    committee_id: 3,
    status: 'draft',
    availability_deadline: null,
    availability_reminder_at: null,
    _links: { self: { href: '/api/exam-rounds/4' } },
  };
}

function apiLifecycle() {
  return {
    round_id: 4,
    revision: 2,
    status: 'closed',
    legacy_status: null,
    historical_without_formal_evidence: false,
    evaluation: {
      ready: true,
      items: [{ code: 'closed', label: 'Abschluss', ok: true, details: null }],
    },
    candidates: [
      {
        round_candidate_id: 8,
        candidate_id: 12,
        terminal_status: 'open',
        terminal_reason: null,
        effective_new_round_id: null,
        postponed_until: null,
        ihk_decision_reference: null,
        terminal_at: null,
      },
    ],
    current_decision: null,
    decisions: [],
    reopenings: [],
    history: [
      { id: 3, round_revision: 2, event_type: 'closed', reason: 'abgeschlossen', created_at: '' },
    ],
    tasks: [],
    exports: [],
    ihk_statuses: [
      {
        id: 5,
        exam_result_id: 9,
        document_status: 'zugestellt',
        document_reference: 'IHK-2',
        recorded_by_member_id: 2,
        recorded_at: '',
      },
    ],
    retention: {
      retain_until: '2036-01-01',
      legal_hold: true,
      sources: [],
    },
    permissions: { close: false, cancel: false, reopen: true, delete: false, export: true },
    _links: { self: { href: '/api/exam-rounds/4/lifecycle' } },
  };
}
