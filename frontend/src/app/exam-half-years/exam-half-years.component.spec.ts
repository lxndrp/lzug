import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideTaiga } from '@taiga-ui/core';

import { ExamHalfYearsComponent } from './exam-half-years.component';
import { athenCommitteeFixture, committeesFixture } from '../testing/fixtures';

describe('ExamHalfYearsComponent', () => {
  let fixture: ComponentFixture<ExamHalfYearsComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ExamHalfYearsComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideTaiga({})],
    }).compileComponents();

    fixture = TestBed.createComponent(ExamHalfYearsComponent);
    fixture.componentRef.setInput('committees', committeesFixture);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('loads terms and creates a committee-specific round', () => {
    const selection = vi
      .spyOn(fixture.componentInstance.roundSelected, 'emit')
      .mockReturnValue(undefined);
    fixture.detectChanges();
    flushInitialLoad(http, [
      { id: 1, season: 'winter', year: 2026, status: 'active' },
      { id: 2, season: 'summer', year: 2027, status: 'draft' },
    ]);
    fixture.detectChanges();

    const host = fixture.nativeElement as HTMLElement;
    const roundForm = Array.from(host.querySelectorAll<HTMLFormElement>('form')).find((form) =>
      form.querySelector('#roundCommittee'),
    )!;
    const committeeSelect = roundForm.querySelector<HTMLSelectElement>('#roundCommittee')!;
    committeeSelect.value = '1';
    committeeSelect.dispatchEvent(new Event('change', { bubbles: true }));
    fixture.detectChanges();
    roundForm.dispatchEvent(new Event('submit'));

    const request = http.expectOne('/api/exam-rounds');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      exam_half_year_id: 1,
      committee_id: 1,
      name: `Winter 2026 · ${athenCommitteeFixture.name}`,
    });
    request.flush({
      id: 2,
      exam_half_year_id: 1,
      committee_id: 1,
      name: `Winter 2026 · ${athenCommitteeFixture.name}`,
      status: 'draft',
      availability_deadline: null,
      availability_reminder_at: null,
    });
    expect(selection).toHaveBeenCalledWith(2);
    flushInitialLoad(http, [
      { id: 1, season: 'winter', year: 2026, status: 'active' },
      { id: 2, season: 'summer', year: 2027, status: 'draft' },
    ]);
  });

  it('creates a round and half-year context atomically from the form values', () => {
    fixture.detectChanges();
    flushInitialLoad(http, []);
    fixture.detectChanges();

    const host = fixture.nativeElement as HTMLElement;
    const halfYearForm = host.querySelector<HTMLFormElement>('form')!;
    halfYearForm.querySelector<HTMLSelectElement>('#examHalfYearSeason')!.value = 'summer';
    halfYearForm.querySelector<HTMLInputElement>('#examHalfYearYear')!.value = '2027';
    halfYearForm.querySelector<HTMLSelectElement>('#newRoundCommittee')!.value = '1';
    halfYearForm.dispatchEvent(new Event('submit'));

    const request = http.expectOne('/api/exam-rounds');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      season: 'summer',
      year: 2027,
      committee_id: 1,
      name: `Sommer 2027 · ${athenCommitteeFixture.name}`,
    });
    request.flush({
      id: 2,
      exam_half_year_id: 2,
      committee_id: 1,
      name: `Sommer 2027 · ${athenCommitteeFixture.name}`,
      status: 'draft',
    });
    flushInitialLoad(http, [{ id: 2, season: 'summer', year: 2027, status: 'active' }]);
  });

  it('keeps every half-year entry and detail read-only in the demo', () => {
    fixture.componentRef.setInput('readOnly', true);
    fixture.detectChanges();
    flushInitialLoad(
      http,
      [{ id: 1, season: 'winter', year: 2026, status: 'active' }],
      [
        {
          id: 1,
          exam_half_year_id: 1,
          committee_id: 1,
          name: 'Winter 2026 · Prüfungsausschuss Teststadt 1',
          status: 'draft',
        },
      ],
    );
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('öffentlichen Demo schreibgeschützt');
    expect(element.textContent).not.toContain('Prüfungsrunde anlegen');
    expect(element.textContent).not.toContain('Bearbeiten');
    expect(element.textContent).not.toContain('Runde abschließen');
    expect(element.textContent).not.toContain('Ausschuss hinzufügen');
    expect(buttonByText(element, 'Öffnen')).toBeDefined();
  });

  it('keeps readable native required selections free of clear actions', () => {
    fixture.detectChanges();
    flushInitialLoad(http, [{ id: 1, season: 'winter', year: 2026, status: 'active' }]);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    for (const selector of ['#examHalfYearSeason', '#newRoundCommittee', '#roundCommittee']) {
      const select = element.querySelector<HTMLSelectElement>(selector)!;
      expect(select.required).toBe(true);
      expect(select.closest('tui-textfield')?.querySelector('[tuiButtonX]')).toBeNull();
      expect(select.options[select.selectedIndex]?.textContent?.trim()).not.toBe('');
    }
  });

  it('shows master-detail counts and progress for the selected half-year', () => {
    fixture.componentRef.setInput('candidateAssignments', [
      {
        id: 1,
        candidate_id: 1,
        exam_half_year_id: 1,
        exam_round_id: 1,
        round_candidate_id: 1,
        assigned_at: '2026-07-01 09:00:00',
        ended_at: null,
        change_reason: null,
      },
      {
        id: 2,
        candidate_id: 2,
        exam_half_year_id: 1,
        exam_round_id: 1,
        round_candidate_id: 2,
        assigned_at: '2026-06-01 09:00:00',
        ended_at: '2026-07-01 09:00:00',
        change_reason: 'Ausschusswechsel',
      },
    ]);
    fixture.detectChanges();
    flushInitialLoad(
      http,
      [{ id: 1, season: 'winter', year: 2026, status: 'active' }],
      [
        {
          id: 1,
          exam_half_year_id: 1,
          committee_id: 1,
          name: 'Winter 2026 · Prüfungsausschuss Teststadt 1',
          status: 'plan_confirmed',
        },
        {
          id: 2,
          exam_half_year_id: 1,
          committee_id: 2,
          name: 'Winter 2026 · Prüfungsausschuss Teststadt 2',
          status: 'draft',
        },
      ],
    );
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('.app-half-year-metrics')?.textContent).toContain('1');
    expect(element.textContent).toContain('1 von 2 Prüfungsrunden bestätigt');
    expect(element.textContent).toContain('Zuordnung im Halbjahr');
    expect(element.textContent).toContain('Prüflinge');
    expect(element.textContent).toContain('Ausschussbezogener Rundenstand');
  });

  it('closes a ready round with its current revision and explicit confirmation', () => {
    fixture.detectChanges();
    flushInitialLoad(
      http,
      [{ id: 1, season: 'winter', year: 2026, status: 'active' }],
      [
        {
          id: 1,
          exam_half_year_id: 1,
          committee_id: 1,
          name: 'Winter 2026 · Prüfungsausschuss Teststadt 1',
          status: 'plan_confirmed',
        },
      ],
      true,
    );
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const confirmation = Array.from(element.querySelectorAll<HTMLInputElement>('input')).find(
      (input) => input.type === 'checkbox',
    )!;
    confirmation.checked = true;
    buttonByText(element, 'Runde abschließen')?.click();

    const request = http.expectOne('/api/exam-rounds/1/closure');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ revision: 1, confirmed: true });
    request.flush(lifecycleFixture('closed', true));
    fixture.detectChanges();
    expect(element.textContent).toContain('Abgeschlossen');
  });

  it('saves terminal candidate states and later IHK document statuses', () => {
    const round = roundFixture();
    fixture.componentRef.setInput('candidates', [
      {
        candidate: {
          id: 7,
          first_name: 'Ada',
          last_name: 'Lovelace',
          ihk_exam_number: 'IHK-7',
          specialization: 'Anwendungsentwicklung',
          training_company: 'Analytical Engines GmbH',
        },
      },
    ]);
    fixture.detectChanges();
    flushInitialLoad(http, [halfYearFixture()], [round]);

    const component = fixture.componentInstance as unknown as {
      candidateName(candidateId: number): string;
      setCandidateTerminalStatus(
        round: object,
        roundCandidateId: number,
        terminalStatus: string,
        reason: string,
        detail: string,
      ): void;
      documentIhkStatus(
        round: object,
        resultId: number,
        documentStatus: string,
        reference: string,
      ): void;
    };
    expect(component.candidateName(7)).toBe('Ada Lovelace');
    expect(component.candidateName(8)).toBe('Prüfling 8');

    component.setCandidateTerminalStatus(
      round,
      11,
      'postponed',
      '  verbindliche Nachplanung  ',
      '2027-12-01',
    );
    const terminalRequest = http.expectOne('/api/exam-rounds/1/candidates/11/terminal-status');
    expect(terminalRequest.request.method).toBe('PUT');
    expect(terminalRequest.request.body).toEqual({
      revision: 1,
      terminal_status: 'postponed',
      reason: 'verbindliche Nachplanung',
      postponed_until: '2027-12-01',
    });
    terminalRequest.flush(lifecycleFixture('open', false));

    component.setCandidateTerminalStatus(round, 11, 'transferred', ' Ausschusswechsel ', '2');
    const transferRequest = http.expectOne('/api/exam-rounds/1/candidates/11/terminal-status');
    expect(transferRequest.request.body).toEqual({
      revision: 1,
      terminal_status: 'transferred',
      reason: 'Ausschusswechsel',
      effective_new_round_id: 2,
    });
    transferRequest.flush(lifecycleFixture('open', false));

    component.setCandidateTerminalStatus(round, 11, 'ihk_terminated', ' Entscheidung ', 'IHK-B-89');
    const terminationRequest = http.expectOne('/api/exam-rounds/1/candidates/11/terminal-status');
    expect(terminationRequest.request.body).toEqual({
      revision: 1,
      terminal_status: 'ihk_terminated',
      reason: 'Entscheidung',
      ihk_decision_reference: 'IHK-B-89',
    });
    terminationRequest.flush(lifecycleFixture('open', false));

    component.documentIhkStatus(round, 21, ' Zugestellt ', ' IHK-89 ');
    const ihkRequest = http.expectOne('/api/exam-rounds/1/results/21/ihk-status');
    expect(ihkRequest.request.method).toBe('PUT');
    expect(ihkRequest.request.body).toEqual({
      document_status: 'Zugestellt',
      document_reference: 'IHK-89',
    });
    ihkRequest.flush(lifecycleFixture('open', false));
  });

  it('cancels, reopens and deletes a round through revision-bound commands', () => {
    const round = roundFixture();
    fixture.detectChanges();
    flushInitialLoad(http, [halfYearFixture()], [round]);

    const component = fixture.componentInstance as unknown as {
      cancelRound(round: object, reason: string, confirmed: boolean): void;
      reopenRound(
        round: object,
        occasion: string,
        source: string,
        reason: string,
        scopeKind: string,
        scopeId: number,
        confirmed: boolean,
      ): void;
      deleteRound(round: object, confirmed: boolean): void;
    };
    component.cancelRound(round, ' Vollständige Absage ', true);
    const cancellation = http.expectOne('/api/exam-rounds/1/cancellation');
    expect(cancellation.request.body).toEqual({
      revision: 1,
      confirmed: true,
      reason: 'Vollständige Absage',
    });
    cancellation.flush(lifecycleFixture('closed', false));

    component.reopenRound(
      round,
      ' Berichtigungsantrag ',
      ' IHK-Vorgang 89 ',
      ' Bezeichnung korrigieren ',
      'planning',
      1,
      true,
    );
    const reopening = http.expectOne('/api/exam-rounds/1/reopenings');
    expect(reopening.request.body).toEqual({
      revision: 2,
      occasion: 'Berichtigungsantrag',
      source: 'IHK-Vorgang 89',
      reason: 'Bezeichnung korrigieren',
      scope: [{ kind: 'planning', entity_id: 1 }],
    });
    const reopened = lifecycleFixture('open', false);
    reopened.permissions.delete = true;
    reopening.flush(reopened);

    component.deleteRound(round, true);
    const rejectedDeletion = http.expectOne('/api/exam-rounds/1');
    rejectedDeletion.flush({}, { status: 409, statusText: 'Conflict' });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Nur eine vollständig leere Entwurfsrunde kann gelöscht werden.',
    );

    component.deleteRound(round, true);
    const acceptedDeletion = http.expectOne('/api/exam-rounds/1');
    expect(acceptedDeletion.request.method).toBe('DELETE');
    acceptedDeletion.flush(null);
    flushInitialLoad(http, [halfYearFixture()], []);
  });

  it('resets creation state and reports load failures', () => {
    fixture.detectChanges();
    http.expectOne('/api/exam-half-years').flush({}, { status: 503, statusText: 'Unavailable' });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Prüfungshalbjahre konnten nicht geladen werden.',
    );

    const component = fixture.componentInstance as unknown as {
      toggleHalfYearCreation(): void;
      cancelHalfYearCreation(): void;
    };
    component.toggleHalfYearCreation();
    component.cancelHalfYearCreation();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).not.toContain('Anlegen abbrechen');
  });
});

function halfYearFixture() {
  return { id: 1, season: 'winter', year: 2026, status: 'active' };
}

function roundFixture() {
  return {
    id: 1,
    exam_half_year_id: 1,
    committee_id: 1,
    name: 'Winter 2026 · Prüfungsausschuss Teststadt 1',
    status: 'draft',
    availability_deadline: null,
    availability_reminder_at: null,
  };
}

function flushInitialLoad(
  http: HttpTestingController,
  halfYears: object[],
  rounds: object[] = [],
  ready = false,
): void {
  http.expectOne('/api/exam-half-years').flush({ items: halfYears, _links: {} });
  http.expectOne('/api/exam-rounds').flush({ items: rounds, _links: {} });
  for (const round of rounds as Array<{ id: number }>) {
    http.expectOne(`/api/exam-rounds/${round.id}/lifecycle`).flush(lifecycleFixture('open', ready));
  }
}

function lifecycleFixture(status: 'open' | 'closed', ready: boolean) {
  return {
    round_id: 1,
    revision: status === 'open' ? 1 : 2,
    status,
    legacy_status: null,
    historical_without_formal_evidence: false,
    evaluation: { ready, items: [{ code: 'ready', label: 'Alle Voraussetzungen', ok: ready }] },
    candidates: [],
    current_decision: null,
    decisions: [],
    reopenings: [],
    history: [],
    tasks: [],
    exports: [],
    ihk_statuses: [],
    retention: { retain_until: null, legal_hold: false, sources: [] },
    permissions: {
      close: status === 'open',
      cancel: status === 'open',
      reopen: status === 'closed',
      delete: false,
      export: true,
    },
    _links: {},
  };
}

function buttonByText(element: HTMLElement, text: string): HTMLButtonElement | undefined {
  return Array.from(element.querySelectorAll<HTMLButtonElement>('button')).find((button) =>
    button.textContent?.includes(text),
  );
}
