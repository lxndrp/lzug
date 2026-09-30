import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Observable, of, throwError } from 'rxjs';
import { provideTaiga } from '@taiga-ui/core';

import { ExamHalfYearsComponent } from './exam-half-years.component';
import { EXAM_HALF_YEARS_PORT, type ExamHalfYearsPort } from './exam-half-years.port';
import type { ExamHalfYear, ExamRound, RoundLifecycle } from './exam-half-years.models';
import { athenCommitteeFixture, committeesFixture } from '../testing/fixtures';

describe('ExamHalfYearsComponent', () => {
  let fixture: ComponentFixture<ExamHalfYearsComponent>;
  let port: ExamHalfYearsPort;

  beforeEach(async () => {
    port = {
      listHalfYears: vi.fn((): Observable<ExamHalfYear[]> => of([])),
      listRounds: vi.fn((): Observable<ExamRound[]> => of([])),
      createRound: vi.fn((): Observable<ExamRound> => of(roundFixture())),
      getRoundLifecycle: vi.fn((): Observable<RoundLifecycle> => of(lifecycleFixture())),
      closeRound: vi.fn((): Observable<RoundLifecycle> => of(lifecycleFixture('closed'))),
      cancelRound: vi.fn((): Observable<RoundLifecycle> => of(lifecycleFixture('cancelled'))),
      reopenRound: vi.fn((): Observable<RoundLifecycle> => of(lifecycleFixture('open'))),
      deleteEmptyRound: vi.fn((): Observable<void> => of(undefined)),
      setCandidateTerminalStatus: vi.fn((): Observable<RoundLifecycle> => of(lifecycleFixture())),
      documentIhkStatus: vi.fn((): Observable<RoundLifecycle> => of(lifecycleFixture())),
      exportLifecycle: vi.fn(() =>
        of({
          content: '{}',
          mediaType: 'application/json; charset=utf-8',
          fileName: 'pruefungsrunde-1-nachweis.json',
        }),
      ),
    };
    await TestBed.configureTestingModule({
      imports: [ExamHalfYearsComponent],
      providers: [provideTaiga({}), { provide: EXAM_HALF_YEARS_PORT, useValue: port }],
    }).compileComponents();

    fixture = TestBed.createComponent(ExamHalfYearsComponent);
    fixture.componentRef.setInput(
      'committees',
      committeesFixture.map(({ id, name }) => ({ id, name })),
    );
  });

  it('loads terms and creates a committee-specific round', () => {
    vi.mocked(port.listHalfYears).mockReturnValue(of([halfYearFixture()]));
    vi.mocked(port.listRounds).mockReturnValue(of([]));
    const selection = vi
      .spyOn(fixture.componentInstance.roundSelected, 'emit')
      .mockReturnValue(undefined);
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

    expect(port.createRound).toHaveBeenCalledWith({
      halfYearId: 1,
      committeeId: 1,
      name: `Winter 2026 · ${athenCommitteeFixture.name}`,
    });
    expect(selection).toHaveBeenCalledWith(1);
  });

  it('creates a half-year context and its committee-specific round atomically', () => {
    fixture.detectChanges();
    const host = fixture.nativeElement as HTMLElement;
    const halfYearForm = host.querySelector<HTMLFormElement>('form')!;
    halfYearForm.querySelector<HTMLSelectElement>('#examHalfYearSeason')!.value = 'summer';
    halfYearForm.querySelector<HTMLInputElement>('#examHalfYearYear')!.value = '2027';
    halfYearForm.querySelector<HTMLSelectElement>('#newRoundCommittee')!.value = '1';
    halfYearForm.dispatchEvent(new Event('submit'));

    expect(port.createRound).toHaveBeenCalledWith({
      season: 'summer',
      year: 2027,
      committeeId: 1,
      name: `Sommer 2027 · ${athenCommitteeFixture.name}`,
    });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Prüfungsrunde und gemeinsamer Halbjahreskontext wurden angelegt.',
    );
  });

  it('keeps every half-year entry and detail read-only in the demo', () => {
    vi.mocked(port.listHalfYears).mockReturnValue(of([halfYearFixture()]));
    vi.mocked(port.listRounds).mockReturnValue(of([roundFixture()]));
    fixture.componentRef.setInput('readOnly', true);
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
    vi.mocked(port.listHalfYears).mockReturnValue(of([halfYearFixture()]));
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    for (const selector of ['#examHalfYearSeason', '#newRoundCommittee', '#roundCommittee']) {
      const select = element.querySelector<HTMLSelectElement>(selector)!;
      expect(select.required).toBe(true);
      expect(select.closest('tui-textfield')?.querySelector('[tuiButtonX]')).toBeNull();
      expect(select.options[select.selectedIndex]?.textContent?.trim()).not.toBe('');
    }
  });

  it('shows candidate counts and progress for the selected half-year', () => {
    vi.mocked(port.listHalfYears).mockReturnValue(of([halfYearFixture()]));
    vi.mocked(port.listRounds).mockReturnValue(
      of([roundFixture(), { ...roundFixture(), id: 2, committeeId: 2, status: 'draft' }]),
    );
    fixture.componentRef.setInput('candidateAssignments', [
      { halfYearId: 1, candidateId: 1, endedAt: null },
      { halfYearId: 1, candidateId: 2, endedAt: '2026-07-01 09:00:00' },
    ]);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('.app-half-year-metrics')?.textContent).toContain('1');
    expect(element.textContent).toContain('1 von 2 Prüfungsrunden bestätigt');
    expect(element.textContent).toContain('Zuordnung im Halbjahr');
    expect(element.textContent).toContain('Prüflinge');
    expect(element.textContent).toContain('Ausschussbezogener Rundenstand');
  });

  it('closes a ready round with its current revision and explicit confirmation', () => {
    vi.mocked(port.listHalfYears).mockReturnValue(of([halfYearFixture()]));
    vi.mocked(port.listRounds).mockReturnValue(of([roundFixture()]));
    vi.mocked(port.getRoundLifecycle).mockReturnValue(of(lifecycleFixture('open', true)));
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const confirmation = Array.from(element.querySelectorAll<HTMLInputElement>('input')).find(
      (input) => input.type === 'checkbox',
    )!;
    confirmation.checked = true;
    buttonByText(element, 'Runde abschließen')?.click();

    expect(port.closeRound).toHaveBeenCalledWith(1, 1);
    fixture.detectChanges();
    expect(element.textContent).toContain('Abgeschlossen');
  });

  it('keeps candidate terminal status and IHK actions behind editable role state', () => {
    vi.mocked(port.listHalfYears).mockReturnValue(of([halfYearFixture()]));
    vi.mocked(port.listRounds).mockReturnValue(of([roundFixture()]));
    vi.mocked(port.getRoundLifecycle).mockReturnValue(
      of({
        ...lifecycleFixture(),
        candidates: [{ roundCandidateId: 11, candidateId: 7, terminalStatus: 'open' }],
      }),
    );
    fixture.componentRef.setInput('candidates', [
      { id: 7, firstName: 'Ada', lastName: 'Lovelace' },
    ]);
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      candidateName(candidateId: number): string;
      setCandidateTerminalStatus(
        round: ExamRound,
        roundCandidateId: number,
        terminalStatus: string,
        reason: string,
        detail: string,
      ): void;
      documentIhkStatus(
        round: ExamRound,
        resultId: number,
        documentStatus: string,
        reference: string,
      ): void;
    };
    expect(component.candidateName(7)).toBe('Ada Lovelace');
    expect(component.candidateName(8)).toBe('Prüfling 8');

    component.setCandidateTerminalStatus(
      roundFixture(),
      11,
      'postponed',
      '  verbindliche Nachplanung  ',
      '2027-12-01',
    );
    expect(port.setCandidateTerminalStatus).toHaveBeenCalledWith(1, 11, {
      revision: 1,
      terminalStatus: 'postponed',
      reason: 'verbindliche Nachplanung',
      postponedUntil: '2027-12-01',
    });

    component.documentIhkStatus(roundFixture(), 21, ' Zugestellt ', ' IHK-89 ');
    expect(port.documentIhkStatus).toHaveBeenCalledWith(1, 21, 'Zugestellt', 'IHK-89');
  });

  it('cancels, reopens and deletes a round through revision-bound commands', () => {
    vi.mocked(port.listHalfYears).mockReturnValue(of([halfYearFixture()]));
    vi.mocked(port.listRounds).mockReturnValue(of([roundFixture()]));
    vi.mocked(port.getRoundLifecycle).mockReturnValue(
      of({
        ...lifecycleFixture(),
        permissions: { ...lifecycleFixture().permissions, delete: true },
      }),
    );
    vi.mocked(port.reopenRound).mockReturnValue(
      of({
        ...lifecycleFixture('open'),
        permissions: { ...lifecycleFixture().permissions, delete: true },
      }),
    );
    vi.mocked(port.deleteEmptyRound)
      .mockReturnValueOnce(throwError(() => new Error('conflict')))
      .mockReturnValueOnce(of(undefined));
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      cancelRound(round: ExamRound, reason: string, confirmed: boolean): void;
      reopenRound(
        round: ExamRound,
        occasion: string,
        source: string,
        reason: string,
        scopeKind: string,
        scopeId: number,
        confirmed: boolean,
      ): void;
      deleteRound(round: ExamRound, confirmed: boolean): void;
    };
    component.cancelRound(roundFixture(), ' Vollständige Absage ', true);
    expect(port.cancelRound).toHaveBeenCalledWith(1, 1, 'Vollständige Absage');

    component.reopenRound(
      roundFixture(),
      ' Berichtigungsantrag ',
      ' IHK-Vorgang 89 ',
      ' Bezeichnung korrigieren ',
      'planning',
      1,
      true,
    );
    expect(port.reopenRound).toHaveBeenCalledWith(1, {
      revision: 2,
      occasion: 'Berichtigungsantrag',
      source: 'IHK-Vorgang 89',
      reason: 'Bezeichnung korrigieren',
      scope: [{ kind: 'planning', entityId: 1 }],
    });

    component.deleteRound(roundFixture(), true);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Nur eine vollständig leere Entwurfsrunde kann gelöscht werden.',
    );
    component.deleteRound(roundFixture(), true);
    fixture.detectChanges();
    expect(port.deleteEmptyRound).toHaveBeenCalledWith(1);
  });

  it('reports load failures and resets creation state', () => {
    vi.mocked(port.listHalfYears).mockReturnValueOnce(throwError(() => new Error('unavailable')));
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

function halfYearFixture(): ExamHalfYear {
  return { id: 1, season: 'winter', year: 2026, status: 'active' };
}

function roundFixture(): ExamRound {
  return {
    id: 1,
    halfYearId: 1,
    committeeId: 1,
    name: 'Winter 2026 · Prüfungsausschuss Teststadt 1',
    status: 'plan_confirmed',
  };
}

function lifecycleFixture(status = 'open', ready = false): RoundLifecycle {
  return {
    roundId: 1,
    revision: status === 'open' ? 1 : 2,
    status,
    historicalWithoutFormalEvidence: false,
    evaluation: { ready, items: [{ code: 'ready', label: 'Alle Voraussetzungen', ok: ready }] },
    candidates: [],
    retention: { retainUntil: null, legalHold: false },
    ihkStatuses: [],
    permissions: {
      close: status === 'open',
      cancel: status === 'open',
      reopen: status === 'closed',
      delete: false,
    },
    history: [],
  };
}

function buttonByText(element: HTMLElement, text: string): HTMLButtonElement | undefined {
  return Array.from(element.querySelectorAll<HTMLButtonElement>('button')).find((button) =>
    button.textContent?.includes(text),
  );
}
