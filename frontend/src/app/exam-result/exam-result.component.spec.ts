import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Observable, Subject, of, throwError } from 'rxjs';
import { provideTaiga } from '@taiga-ui/core';

import { ApplicationError } from '../application/application-error';
import { AuthService } from '../auth/auth.service';
import { EXAM_RESULT_PORT, type ExamResultPort } from './exam-result.port';
import type { ExamResult } from './exam-result.models';
import { ExamResultComponent } from './exam-result.component';

describe('ExamResultComponent', () => {
  let fixture: ComponentFixture<ExamResultComponent>;
  let port: ExamResultPort;

  beforeEach(async () => {
    port = {
      get: vi.fn((): Observable<ExamResult> => of(resultFixture())),
      saveIndividualAssessment: vi.fn(() => of(resultFixture())),
      withdrawIndividualAssessment: vi.fn(() => of(resultFixture())),
      discloseAssessments: vi.fn(() => of(resultFixture())),
      determineComponent: vi.fn(() => of(resultFixture())),
      recordExternalResult: vi.fn(() => of(resultFixture())),
      confirmExternalResult: vi.fn(() => of(resultFixture())),
      determineExamResult: vi.fn(() => of(resultFixture())),
      confirmResultRecord: vi.fn(() => of(resultFixture())),
      openResultCorrection: vi.fn(() => of(resultFixture())),
      communicateExamResult: vi.fn(() => of(resultFixture())),
      setExamResultRetention: vi.fn(() => of(resultFixture())),
    };
    await TestBed.configureTestingModule({
      imports: [ExamResultComponent],
      providers: [provideTaiga({}), { provide: EXAM_RESULT_PORT, useValue: port }],
    }).compileComponents();
    fixture = TestBed.createComponent(ExamResultComponent);
    fixture.componentRef.setInput('roundId', 1);
    fixture.componentRef.setInput('dayId', 7);
    fixture.componentRef.setInput('dayRevision', 4);
    fixture.componentRef.setInput('slotId', 11);
    fixture.componentRef.setInput('ownMemberId', 1);
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 2,
      person_id: 3,
      committee_member_id: 1,
      is_operator: false,
      capabilities: [
        'exam-result:read',
        'exam-result:assess-own',
        'exam-result:disclose',
        'exam-result:determine-component',
        'exam-result:external-record',
        'exam-result:external-confirm',
        'exam-result:determine',
        'exam-result:confirm-record',
        'exam-result:coordinate-correction',
        'exam-result:communicate',
        'exam-result:retention',
        'exam-result:export',
      ],
    });
  });

  it('renders the model and submits an own assessment through the feature port', () => {
    fixture.detectChanges();
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(port.get).toHaveBeenCalledWith(7, 11);
    expect(element.textContent).toContain('Regelgebundener Ergebnisprozess');
    expect(element.textContent).toContain('Eigene Bewertungsbegründungen');
    expect(element.textContent).toContain('Modellversion');

    const component = fixture.componentInstance as unknown as {
      drafts: Map<string, { rawPoints: string; rationale: string; changeReason: string }>;
      saveAssessment(
        model: ExamResult['modelVersion']['rules']['components'][number],
        criterion: ExamResult['modelVersion']['rules']['components'][number]['criteria'][number],
        submitted: boolean,
      ): void;
    };
    component.drafts.set('documentation:clarity', {
      rawPoints: '82',
      rationale: 'Beobachtung',
      changeReason: '',
    });
    component.saveAssessment(
      resultFixture().modelVersion.rules.components[0],
      criterionFixture(),
      true,
    );

    expect(port.saveIndividualAssessment).toHaveBeenCalledWith({
      resultId: 41,
      version: 3,
      componentKey: 'documentation',
      criterionKey: 'clarity',
      rawPoints: '82',
      rationale: 'Beobachtung',
      submitted: true,
      changeReason: '',
      dayRevisions: { '7': 4 },
    });
  });

  it('returns accepted day revisions to the examination-day owner', () => {
    const changes: Array<Record<string, number>> = [];
    fixture.componentInstance.dayRevisionsChanged.subscribe((revisions) => changes.push(revisions));
    vi.mocked(port.saveIndividualAssessment).mockReturnValueOnce(
      of(resultFixture({ dayRevisions: { '7': 5 } })),
    );
    fixture.detectChanges();
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      drafts: Map<string, { rawPoints: string; rationale: string; changeReason: string }>;
      saveAssessment(
        model: ExamResult['modelVersion']['rules']['components'][number],
        criterion: ExamResult['modelVersion']['rules']['components'][number]['criteria'][number],
        submitted: boolean,
      ): void;
    };
    component.drafts.set('documentation:clarity', {
      rawPoints: '82',
      rationale: 'Beobachtung',
      changeReason: '',
    });
    component.saveAssessment(
      resultFixture().modelVersion.rules.components[0],
      criterionFixture(),
      true,
    );

    expect(changes).toEqual([{ '7': 5 }]);
  });

  it('keeps a pending command and vote drafts across a day-only revision refresh', () => {
    const pending = new Subject<ExamResult>();
    vi.mocked(port.saveIndividualAssessment).mockReturnValueOnce(pending.asObservable());
    fixture.detectChanges();
    fixture.detectChanges();
    const component = fixture.componentInstance as unknown as {
      busy: () => boolean;
      error: () => string | null;
      componentVotes: Map<string, Map<number, 'yes' | 'no' | 'abstain'>>;
      componentVoters: Map<string, Set<number>>;
      examResultVotes: Map<number, 'yes' | 'no' | 'abstain'>;
      examResultVoters: Set<number>;
      saveAssessment(
        model: ExamResult['modelVersion']['rules']['components'][number],
        criterion: ExamResult['modelVersion']['rules']['components'][number]['criteria'][number],
        submitted: boolean,
      ): void;
    };
    component.componentVotes.set('documentation', new Map([[1, 'yes']]));
    component.componentVoters.set('documentation', new Set([1]));
    component.examResultVotes.set(1, 'no');
    component.examResultVoters.add(1);
    component.saveAssessment(
      resultFixture().modelVersion.rules.components[0],
      criterionFixture(),
      true,
    );
    expect(component.busy()).toBe(true);

    fixture.componentRef.setInput('dayRevision', 5);
    fixture.detectChanges();
    expect(component.busy()).toBe(true);
    expect(component.componentVotes.get('documentation')?.get(1)).toBe('yes');
    expect(component.componentVoters.get('documentation')?.has(1)).toBe(true);
    expect(component.examResultVotes.get(1)).toBe('no');
    expect(component.examResultVoters.has(1)).toBe(true);

    pending.error(new ApplicationError('conflict', 'Die Tagesrevision wurde geändert.'));
    fixture.detectChanges();

    expect(component.busy()).toBe(false);
    expect(component.error()).toBe('Die Tagesrevision wurde geändert.');
    expect(component.componentVotes.get('documentation')?.get(1)).toBe('yes');
    expect(component.examResultVotes.get(1)).toBe('no');
    expect(port.get).toHaveBeenCalledTimes(2);
  });

  it('preserves a dirty component-points draft across a day revision reload', () => {
    const initial = resultFixture({
      committeeAssessments: [committeeAssessment('78')],
    });
    const refreshed = resultFixture({
      dayRevisions: { '7': 5 },
      committeeAssessments: [committeeAssessment('82')],
    });
    vi.mocked(port.get).mockReturnValueOnce(of(initial)).mockReturnValueOnce(of(refreshed));
    fixture.detectChanges();
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      componentPoints: Map<string, string>;
    };
    component.componentPoints.set('documentation', '74');
    fixture.componentRef.setInput('dayRevision', 5);
    fixture.detectChanges();

    expect(component.componentPoints.get('documentation')).toBe('74');
  });

  it('preserves dirty retention drafts across a day revision reload', () => {
    const initial = resultFixture({
      committeeAssessments: [committeeAssessment('78')],
      retention: {
        ruleReference: 'Prüfungsordnung',
        periodStart: '2026-01-01',
        retainUntil: '2036-01-01',
        legalHold: false,
        holdReason: null,
      },
    });
    const refreshed = resultFixture({
      dayRevisions: { '7': 5 },
      committeeAssessments: [committeeAssessment('82')],
      retention: {
        ruleReference: 'Prüfungsordnung',
        periodStart: '2026-02-01',
        retainUntil: '2037-01-01',
        legalHold: true,
        holdReason: 'Neuer Rechtsbehelf',
      },
    });
    vi.mocked(port.get)
      .mockReturnValueOnce(of(initial))
      .mockReturnValueOnce(
        throwError(() => new ApplicationError('unavailable', 'Reload fehlgeschlagen.')),
      )
      .mockReturnValueOnce(of(refreshed));
    fixture.detectChanges();
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      retentionPeriodStart: string;
      retentionUntil: string;
      retentionLegalHold: boolean;
      retentionHoldReason: string;
      componentPoints: Map<string, string>;
      state: () => string;
    };
    component.componentPoints.set('documentation', '74');
    component.retentionPeriodStart = '2026-03-15';
    component.retentionUntil = '2038-03-15';
    component.retentionLegalHold = true;
    component.retentionHoldReason = 'Manuelle Notiz';
    fixture.componentRef.setInput('dayRevision', 5);
    fixture.detectChanges();
    expect(component.state()).toBe('error');

    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('button')!.click();
    fixture.detectChanges();

    expect(component.retentionPeriodStart).toBe('2026-03-15');
    expect(component.retentionUntil).toBe('2038-03-15');
    expect(component.retentionLegalHold).toBe(true);
    expect(component.retentionHoldReason).toBe('Manuelle Notiz');
    expect(component.componentPoints.get('documentation')).toBe('74');
    expect(component.state()).toBe('ready');
  });

  it('hides mutation and export controls without the matching capability', () => {
    TestBed.inject(AuthService).session.update((session) => ({
      ...session!,
      capabilities: ['exam-result:read'],
    }));
    fixture.detectChanges();
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).not.toContain('Eigene Bewertung abgeben');
    expect(element.textContent).not.toContain('Vollständige Einzelbewertungen offenlegen');
    expect(element.textContent).not.toContain('Maschinenlesbarer Ergebnisexport');
  });

  it('offers four-eyes confirmation only to a different authorized member', () => {
    vi.mocked(port.get).mockReturnValue(
      of(
        resultFixture({
          externalResults: [
            {
              id: 12,
              areaKey: 'practice',
              revision: 1,
              points: '80',
              grade: null,
              professionalStatus: 'verbindlich',
              determiningAuthority: 'IHK',
              sourceReference: 'Bescheid',
              status: 'unconfirmed',
              recordedByMemberId: 1,
              confirmedByMemberId: null,
              correctionReason: null,
            },
          ],
          permissions: { ...resultFixture().permissions, manageExternal: true },
        }),
      ),
    );
    fixture.componentRef.setInput('ownMemberId', 2);
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 3,
      person_id: 2,
      committee_member_id: 2,
      is_operator: false,
      capabilities: ['exam-result:read', 'exam-result:external-confirm'],
    });
    fixture.detectChanges();
    fixture.detectChanges();

    const button = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    ).find((item) => item.textContent?.trim() === 'Unabhängig bestätigen');
    expect(button).toBeTruthy();
    button?.click();
    expect(port.confirmExternalResult).toHaveBeenCalledWith(41, 3, 12, { '7': 4 });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Externes Eingangsergebnis unabhängig bestätigt.',
    );
  });

  it('distinguishes an unbound result from a retryable loading failure', () => {
    vi.mocked(port.get)
      .mockReturnValueOnce(throwError(() => ({ kind: 'not-found' })))
      .mockReturnValueOnce(throwError(() => new Error('failed')))
      .mockReturnValueOnce(of(resultFixture()));
    fixture.detectChanges();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'noch kein Bewertungsmodell gebunden',
    );
    (fixture.componentInstance as unknown as { load(): void }).load();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Ergebnisprozess konnte nicht geladen werden',
    );
    (fixture.componentInstance as unknown as { load(): void }).load();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Regelgebundener Ergebnisprozess',
    );
  });

  it('requires a complete vote and a simple majority before determining the result', () => {
    fixture.detectChanges();
    fixture.detectChanges();
    const component = fixture.componentInstance as unknown as {
      determineResult(): void;
      setExamResultVoter(memberId: number, selected: boolean): void;
      setExamResultVote(memberId: number, choice: 'yes' | 'no' | 'abstain' | null): void;
    };

    component.determineResult();
    fixture.detectChanges();
    expect(port.determineExamResult).not.toHaveBeenCalled();
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[role="alert"]')?.textContent,
    ).toContain('mindestens die erforderliche Anzahl anwesender Ausschussmitglieder');

    component.setExamResultVoter(1, true);
    component.setExamResultVoter(2, true);
    component.setExamResultVote(1, 'yes');
    component.setExamResultVote(2, 'no');
    component.determineResult();
    fixture.detectChanges();
    expect(port.determineExamResult).not.toHaveBeenCalled();
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[role="alert"]')?.textContent,
    ).toContain('mehr Ja- als Nein-Stimmen');

    component.setExamResultVote(2, 'abstain');
    component.determineResult();
    expect(port.determineExamResult).toHaveBeenCalledWith(
      expect.objectContaining({ vote: { yes: [1], no: [], abstain: [2] } }),
    );
  });

  it('passes the explicit majority and independent dissent through both feature commands', () => {
    const disclosedResult = resultFixture({
      participants: [1, 2, 3],
      disclosures: [
        { componentKey: 'documentation', disclosedByMemberId: 1, disclosedAt: '2026-09-30' },
      ],
    });
    vi.mocked(port.get).mockReturnValue(of(disclosedResult));
    vi.mocked(port.determineComponent).mockReturnValue(of(disclosedResult));
    fixture.detectChanges();
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      determineComponent(key: string): void;
      determineResult(): void;
      componentVotes: Map<string, Map<number, 'yes' | 'no' | 'abstain'>>;
      componentVoters: Map<string, Set<number>>;
      examResultVotes: Map<number, 'yes' | 'no' | 'abstain'>;
      examResultVoters: Set<number>;
      dissentMemberId: number | null;
      dissentStatement: string;
    };
    const vote = new Map<number, 'yes' | 'no' | 'abstain'>([
      [1, 'yes'],
      [2, 'yes'],
      [3, 'no'],
    ]);
    component.componentVotes.set('documentation', vote);
    component.componentVoters.set('documentation', new Set([1, 2, 3]));
    component.examResultVotes.set(1, 'yes');
    component.examResultVotes.set(2, 'yes');
    component.examResultVotes.set(3, 'no');
    component.examResultVoters.add(1);
    component.examResultVoters.add(2);
    component.examResultVoters.add(3);
    component.dissentMemberId = 3;
    component.dissentStatement = 'Abweichende Begründung';

    component.determineComponent('documentation');
    expect(port.determineComponent).toHaveBeenCalledWith(
      expect.objectContaining({
        participants: [1, 2, 3],
        vote: { yes: [1, 2], no: [3], abstain: [] },
        dissent: [{ memberId: 3, statement: 'Abweichende Begründung' }],
      }),
    );

    component.determineResult();
    expect(port.determineExamResult).toHaveBeenCalledWith(
      expect.objectContaining({
        participants: [1, 2, 3],
        vote: { yes: [1, 2], no: [3], abstain: [] },
        dissent: [{ memberId: 3, statement: 'Abweichende Begründung' }],
      }),
    );
  });

  it('sends only the selected quorum and clears votes after determination', () => {
    const disclosedResult = resultFixture({
      participants: [1, 2, 3],
      disclosures: [
        { componentKey: 'documentation', disclosedByMemberId: 1, disclosedAt: '2026-09-30' },
      ],
    });
    vi.mocked(port.get).mockReturnValue(of(disclosedResult));
    vi.mocked(port.determineComponent).mockReturnValue(of(disclosedResult));
    vi.mocked(port.determineExamResult).mockReturnValue(of(disclosedResult));
    fixture.detectChanges();
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      determineComponent(key: string): void;
      determineResult(): void;
      componentVotes: Map<string, Map<number, 'yes' | 'no' | 'abstain'>>;
      componentVoters: Map<string, Set<number>>;
      examResultVotes: Map<number, 'yes' | 'no' | 'abstain'>;
      examResultVoters: Set<number>;
    };
    component.componentVoters.set('documentation', new Set([1, 2]));
    component.componentVotes.set(
      'documentation',
      new Map([
        [1, 'yes'],
        [2, 'yes'],
      ]),
    );
    component.examResultVoters.add(1);
    component.examResultVoters.add(2);
    component.examResultVotes.set(1, 'yes');
    component.examResultVotes.set(2, 'yes');

    component.determineComponent('documentation');
    expect(port.determineComponent).toHaveBeenCalledWith(
      expect.objectContaining({
        participants: [1, 2],
        vote: { yes: [1, 2], no: [], abstain: [] },
      }),
    );
    expect(component.componentVotes.has('documentation')).toBe(false);
    expect(component.componentVoters.has('documentation')).toBe(false);

    component.determineResult();
    expect(port.determineExamResult).toHaveBeenCalledWith(
      expect.objectContaining({
        participants: [1, 2],
        vote: { yes: [1, 2], no: [], abstain: [] },
      }),
    );
    expect(component.examResultVotes.size).toBe(0);
    expect(component.examResultVoters.size).toBe(0);
  });

  it('rejects dissent from a member outside the selected quorum in both ballots', () => {
    const disclosedResult = resultFixture({
      participants: [1, 2, 3],
      disclosures: [
        { componentKey: 'documentation', disclosedByMemberId: 1, disclosedAt: '2026-09-30' },
      ],
    });
    vi.mocked(port.get).mockReturnValue(of(disclosedResult));
    fixture.detectChanges();
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      determineComponent(key: string): void;
      determineResult(): void;
      componentVoters: Map<string, Set<number>>;
      componentVotes: Map<string, Map<number, 'yes' | 'no' | 'abstain'>>;
      examResultVoters: Set<number>;
      examResultVotes: Map<number, 'yes' | 'no' | 'abstain'>;
      dissentMemberId: number | null;
      dissentStatement: string;
    };
    component.componentVoters.set('documentation', new Set([1, 2]));
    component.componentVotes.set(
      'documentation',
      new Map([
        [1, 'yes'],
        [2, 'yes'],
      ]),
    );
    component.examResultVoters.add(1);
    component.examResultVoters.add(2);
    component.examResultVotes.set(1, 'yes');
    component.examResultVotes.set(2, 'yes');
    component.dissentMemberId = 3;
    component.dissentStatement = 'Abweichender Standpunkt';

    component.determineComponent('documentation');
    component.determineResult();
    fixture.detectChanges();

    expect(port.determineComponent).not.toHaveBeenCalled();
    expect(port.determineExamResult).not.toHaveBeenCalled();
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[role="alert"]')?.textContent,
    ).toContain('nur ein ausgewähltes anwesendes Mitglied');

    component.dissentMemberId = 2;
    component.determineComponent('documentation');
    expect(port.determineComponent).toHaveBeenCalledWith(
      expect.objectContaining({ dissent: [{ memberId: 2, statement: 'Abweichender Standpunkt' }] }),
    );
    component.determineResult();
    expect(port.determineExamResult).toHaveBeenCalledWith(
      expect.objectContaining({ dissent: [{ memberId: 2, statement: 'Abweichender Standpunkt' }] }),
    );
  });

  it('allows record confirmation only for members in the saved determination quorum', () => {
    const determination = resultFixture().determinations[0];
    vi.mocked(port.get).mockReturnValue(of(resultFixture({ currentDetermination: determination })));
    fixture.componentRef.setInput('ownMemberId', 3);
    fixture.detectChanges();
    fixture.detectChanges();
    expect(
      (fixture.nativeElement as HTMLElement).querySelector(
        'button[aria-label="Sachliche Richtigkeit bestätigen"]',
      ),
    ).toBeNull();
    expect((fixture.nativeElement as HTMLElement).textContent).not.toContain(
      'Sachliche Richtigkeit bestätigen',
    );

    fixture.componentRef.setInput('ownMemberId', 1);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Sachliche Richtigkeit bestätigen',
    );
  });

  it('clears both ballots when a correction is successfully opened', () => {
    vi.mocked(port.openResultCorrection).mockReturnValue(
      of(resultFixture({ correctionOpen: true })),
    );
    fixture.detectChanges();
    fixture.detectChanges();
    const component = fixture.componentInstance as unknown as {
      openCorrection(): void;
      componentVotes: Map<string, Map<number, 'yes' | 'no' | 'abstain'>>;
      componentVoters: Map<string, Set<number>>;
      examResultVotes: Map<number, 'yes' | 'no' | 'abstain'>;
      examResultVoters: Set<number>;
    };
    component.componentVotes.set('documentation', new Map([[1, 'yes']]));
    component.componentVoters.set('documentation', new Set([1]));
    component.examResultVotes.set(1, 'yes');
    component.examResultVoters.add(1);

    component.openCorrection();

    expect(component.componentVotes.size).toBe(0);
    expect(component.componentVoters.size).toBe(0);
    expect(component.examResultVotes.size).toBe(0);
    expect(component.examResultVoters.size).toBe(0);
  });

  it('renders calculation, correction, retention, and immutable result history', () => {
    vi.mocked(port.get).mockReturnValue(
      of(
        resultFixture({
          correctionOpen: true,
          disclosures: [
            { componentKey: 'documentation', disclosedByMemberId: 1, disclosedAt: '2026-09-30' },
          ],
          committeeAssessments: [
            {
              id: 71,
              componentKey: 'documentation',
              revision: 1,
              points: '78',
              rationale: 'Beschluss',
              participantMemberIds: [1, 2],
              vote: { yes: [1, 2], no: [], abstain: [] },
              dissent: [],
              status: 'current',
              determinedAt: '2026-09-30T12:00:00Z',
            },
          ],
          externalResults: [
            {
              id: 12,
              areaKey: 'written',
              revision: 1,
              points: '83',
              grade: 'gut',
              professionalStatus: 'confirmed',
              determiningAuthority: 'IHK',
              sourceReference: 'Bescheid',
              status: 'confirmed',
              recordedByMemberId: 1,
              confirmedByMemberId: 2,
              correctionReason: null,
            },
          ],
          currentCalculation: {
            id: 91,
            version: 3,
            totalPoints: '76.25',
            grade: 'gut',
            passed: true,
            path: {
              inputs: [{ kind: 'component', key: 'documentation', points: '78', weight: '50' }],
              unroundedTotal: '76.25',
              roundedTotal: '76.25',
              thresholdBasis: 'unrounded',
            },
          },
          exports: [
            {
              id: 99,
              resultDeterminationId: 61,
              exportKind: 'machine',
              status: 'superseded',
              generatedAt: '2026-09-30T12:00:00Z',
            },
          ],
          retention: {
            ruleReference: 'Prüfungsordnung',
            periodStart: '2026-01-01',
            retainUntil: '2036-01-01',
            legalHold: true,
            holdReason: 'Rechtsbehelf offen',
          },
        }),
      ),
    );
    fixture.detectChanges();
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Berechnungsbereit');
    expect(element.textContent).toContain('Korrektur offen');
    expect(element.textContent).toContain('Gemeinsame Ausschussbewertung');
    expect(element.textContent).toContain('Offengelegt');
    expect(element.textContent).toContain('76.25 Punkte · gut');
    expect(element.textContent).toContain('Unrunder Zwischenstand 76.25');
    expect(element.textContent).toContain('written · 83 Punkte · confirmed');
    expect(element.textContent).toContain('Maschinenlesbarer Ergebnisexport');
    expect(element.textContent).toContain('Export machine · superseded');
  });

  it('routes all result workflow commands through the feature port', () => {
    vi.mocked(port.get).mockReturnValue(
      of(
        resultFixture({
          individualAssessments: [
            {
              id: 21,
              componentKey: 'documentation',
              criterionKey: 'clarity',
              assessorMemberId: 1,
              revision: 1,
              rawPoints: '75',
              normalizedPoints: '75',
              rationale: 'Begründung',
              status: 'submitted',
              changeReason: null,
              submittedAt: '2026-09-30T12:00:00Z',
            },
          ],
          externalResults: [
            {
              id: 12,
              areaKey: 'practice',
              revision: 1,
              points: '80',
              grade: null,
              professionalStatus: 'verbindlich',
              determiningAuthority: 'IHK',
              sourceReference: 'Bescheid',
              status: 'unconfirmed',
              recordedByMemberId: 2,
              confirmedByMemberId: null,
              correctionReason: null,
            },
          ],
          permissions: {
            ...resultFixture().permissions,
            manageExternal: true,
          },
        }),
      ),
    );
    fixture.detectChanges();
    fixture.detectChanges();
    const component = fixture.componentInstance as unknown as {
      withdraw(
        component: ExamResult['modelVersion']['rules']['components'][number],
        criterion: ExamResult['modelVersion']['rules']['components'][number]['criteria'][number],
      ): void;
      disclose(key: string): void;
      determineComponent(key: string): void;
      recordExternal(): void;
      confirmExternal(id: number): void;
      determineResult(): void;
      confirmRecord(): void;
      openCorrection(): void;
      communicate(): void;
      saveRetention(): void;
      componentPoints: Map<string, string>;
      drafts: Map<string, { rawPoints: string; rationale: string; changeReason: string }>;
      externalAreaKey: string;
      externalPoints: string;
      externalAuthority: string;
      externalSource: string;
      correctionReason: string;
      reopeningReference: string;
      communicationAt: string;
      componentVotes: Map<string, Map<number, 'yes' | 'no' | 'abstain'>>;
      componentVoters: Map<string, Set<number>>;
      examResultVotes: Map<number, 'yes' | 'no' | 'abstain'>;
      examResultVoters: Set<number>;
      dissentMemberId: number | null;
      dissentStatement: string;
    };
    component.componentPoints.set('documentation', '78');
    component.componentVotes.set(
      'documentation',
      new Map([
        [1, 'yes'],
        [2, 'abstain'],
      ]),
    );
    component.componentVoters.set('documentation', new Set([1, 2]));
    component.examResultVotes.set(1, 'yes');
    component.examResultVotes.set(2, 'abstain');
    component.examResultVoters.add(1);
    component.examResultVoters.add(2);
    component.dissentMemberId = 2;
    component.dissentStatement = 'Abweichende Begründung';
    component.drafts.set('documentation:clarity', {
      rawPoints: '75',
      rationale: 'Begründung',
      changeReason: 'Rücknahmegrund',
    });
    component.externalAreaKey = 'practice';
    component.externalPoints = '80';
    component.externalAuthority = 'IHK';
    component.externalSource = 'Bescheid';
    component.correctionReason = 'Grund';
    component.reopeningReference = 'Nachweis';
    component.communicationAt = '2026-09-30T12:00';

    component.withdraw(resultFixture().modelVersion.rules.components[0], criterionFixture());
    component.disclose('documentation');
    component.determineComponent('documentation');
    component.recordExternal();
    component.confirmExternal(12);
    component.determineResult();
    component.confirmRecord();
    component.openCorrection();
    component.communicate();
    component.saveRetention();

    expect(port.withdrawIndividualAssessment).toHaveBeenCalledWith(41, 3, 21, 'Rücknahmegrund', {
      '7': 4,
    });
    expect(port.discloseAssessments).toHaveBeenCalledWith(41, 3, 'documentation', { '7': 4 });
    expect(port.determineComponent).toHaveBeenCalledWith(
      expect.objectContaining({
        resultId: 41,
        componentKey: 'documentation',
        participants: [1, 2],
        vote: { yes: [1], no: [], abstain: [2] },
        dissent: [{ memberId: 2, statement: 'Abweichende Begründung' }],
        dayRevisions: { '7': 4 },
      }),
    );
    expect(port.recordExternalResult).toHaveBeenCalledWith(
      expect.objectContaining({
        resultId: 41,
        areaKey: 'practice',
        determiningAuthority: 'IHK',
      }),
    );
    expect(port.confirmExternalResult).toHaveBeenCalledWith(41, 3, 12, { '7': 4 });
    expect(port.determineExamResult).toHaveBeenCalledWith(
      expect.objectContaining({
        resultId: 41,
        participants: [1, 2],
        vote: { yes: [1], no: [], abstain: [2] },
        dissent: [{ memberId: 2, statement: 'Abweichende Begründung' }],
      }),
    );
    expect(port.confirmResultRecord).toHaveBeenCalledWith(41, 3, { '7': 4 });
    expect(port.openResultCorrection).toHaveBeenCalledWith(41, 3, 'Grund', 'Nachweis', { '7': 4 });
    expect(port.communicateExamResult).toHaveBeenCalledWith(
      41,
      3,
      'persönlich',
      '2026-09-30T12:00',
      '',
      { '7': 4 },
    );
    expect(port.setExamResultRetention).toHaveBeenCalledWith(
      expect.objectContaining({
        resultId: 41,
        legalHold: false,
        dayRevisions: { '7': 4 },
      }),
    );

    vi.mocked(port.determineExamResult).mockReturnValueOnce(
      throwError(() => new ApplicationError('conflict', 'Versionskonflikt')),
    );
    component.examResultVoters.add(1);
    component.examResultVoters.add(2);
    component.examResultVotes.set(1, 'yes');
    component.examResultVotes.set(2, 'abstain');
    component.determineResult();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Versionskonflikt');
  });
});

function criterionFixture(): ExamResult['modelVersion']['rules']['components'][number]['criteria'][number] {
  return { key: 'clarity', label: 'Klarheit', rawMin: '0', rawMax: '100', weight: '100' };
}

function resultFixture(overrides: Partial<ExamResult> = {}): ExamResult {
  const determination: ExamResult['determinations'][number] = {
    id: 61,
    revision: 1,
    participantMemberIds: [1, 2],
    vote: { yes: [1, 2], no: [], abstain: [] },
    dissent: [],
    status: 'current',
    determinedAt: '2026-09-30T12:00:00Z',
    confirmationMemberIds: [],
  };
  return {
    id: 41,
    roundCandidateId: 5,
    dayRevisions: { '7': 4 },
    version: 3,
    state: 'calculation_ready',
    correctionOpen: false,
    legacyStatus: null,
    candidate: {
      id: 5,
      firstName: 'Ada',
      lastName: 'Beispiel',
      ihkExamNumber: '123',
      specialization: 'Anwendung',
    },
    modelVersion: {
      id: 2,
      modelKey: 'standard',
      version: 1,
      ihk: 'IHK Beispiel',
      occupation: 'Fachinformatikerin',
      specialization: null,
      validFrom: '2026-01-01',
      validUntil: null,
      rules: {
        components: [
          {
            key: 'documentation',
            label: 'Dokumentation',
            mode: 'committee',
            weight: '100',
            dayScoped: false,
            requiredAssessors: 2,
            maxDeviation: '20',
            additionalAssessorOnDeviation: false,
            criteria: [criterionFixture()],
          },
        ],
        externalAreas: [{ key: 'practice', label: 'Praxis', weight: '0', required: false }],
        rounding: {
          intermediate: { mode: 'none', digits: null },
          overall: { mode: 'none', digits: null },
          thresholdBasis: 'unrounded',
        },
        grades: [{ label: 'Gut', minPoints: '80' }],
        passing: { overallMin: '50', componentMinima: {}, externalMinima: {} },
        quorum: { minimumMembers: 2, majority: 'simple' },
      },
      retentionRuleReference: 'Prüfungsordnung',
      retentionYears: 10,
    },
    participants: [1, 2],
    disclosures: [],
    individualAssessments: [],
    individualAssessmentCounts: [],
    committeeAssessments: [],
    externalResults: [],
    currentCalculation: {
      id: 91,
      version: 3,
      totalPoints: '78',
      grade: 'Befriedigend',
      passed: true,
      path: {
        inputs: [{ kind: 'component', key: 'documentation', points: '78', weight: '100' }],
        unroundedTotal: '78',
        roundedTotal: '78',
        thresholdBasis: 'unrounded',
      },
    },
    determinations: [determination],
    currentDetermination: null,
    corrections: [],
    communications: [],
    retention: null,
    exports: [],
    permissions: {
      assessOwn: true,
      disclose: true,
      determineComponent: true,
      manageExternal: false,
      determineResult: true,
      confirmRecord: true,
      coordinateCorrection: true,
      communicate: true,
      manageRetention: true,
    },
    exportsLinks: {
      machine: '/api/exam-results/41/export.json',
      human: '/api/exam-results/41/export.txt',
    },
    ...overrides,
  };
}

function committeeAssessment(points: string): ExamResult['committeeAssessments'][number] {
  return {
    id: 71,
    componentKey: 'documentation',
    revision: 1,
    points,
    rationale: 'Beschluss',
    participantMemberIds: [1, 2],
    vote: { yes: [1, 2], no: [], abstain: [] },
    dissent: [],
    status: 'current',
    determinedAt: '2026-09-30T12:00:00Z',
  };
}
