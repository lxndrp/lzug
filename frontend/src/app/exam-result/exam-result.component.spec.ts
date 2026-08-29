import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';

import { AssessmentComponent, AssessmentCriterion, ExamResult } from '../api/api.models';
import { AuthService } from '../auth/auth.service';
import { ExamResultComponent } from './exam-result.component';

describe('ExamResultComponent', () => {
  let fixture: ComponentFixture<ExamResultComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ExamResultComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTaiga({ scrollbars: 'native' }),
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(ExamResultComponent);
    fixture.componentRef.setInput('dayId', 7);
    fixture.componentRef.setInput('slotId', 11);
    fixture.componentRef.setInput('ownMemberId', 1);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('explains the privacy boundary and submits only the own criterion assessment', () => {
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 1,
      person_id: 1,
      committee_member_id: 1,
      is_operator: false,
      capabilities: ['exam-result:read', 'exam-result:assess-own', 'exam-result:export'],
    });
    fixture.detectChanges();
    const result = resultFixture();
    http.expectOne('/api/confirmed-plan-days/7/slots/11/result').flush(result);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Regelgebundener Ergebnisprozess');
    expect(element.textContent).toContain('Andere Einzelbewertungen bleiben');
    expect(element.textContent).toContain('Unabhängige Mehrfachbewertung');
    expect(element.textContent).toContain('Maschinenlesbarer Ergebnisexport');

    const component = result.model_version.rules.components[0];
    const criterion = component.criteria[0];
    const instance = fixture.componentInstance as unknown as {
      draftFor(
        component: AssessmentComponent,
        criterion: AssessmentCriterion,
      ): {
        rawPoints: string;
        rationale: string;
        changeReason: string;
      };
      saveAssessment(
        component: AssessmentComponent,
        criterion: AssessmentCriterion,
        submitted: boolean,
      ): void;
    };
    const draft = instance.draftFor(component, criterion);
    draft.rawPoints = '8.5';
    draft.rationale = 'Nachvollziehbare fachliche Beobachtung';
    instance.saveAssessment(component, criterion, true);

    const request = http.expectOne('/api/exam-results/41/individual-assessments');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      version: 4,
      component_key: 'documentation',
      criterion_key: 'quality',
      raw_points: '8.5',
      rationale: 'Nachvollziehbare fachliche Beobachtung',
      submitted: true,
    });
    request.flush(resultFixture({ version: 5 }));
    fixture.detectChanges();
    expect(element.textContent).toContain('Eigene Bewertung abgegeben.');
  });

  it('does not expose result mutations without their precise demo capabilities', () => {
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 2,
      person_id: 3,
      committee_member_id: 3,
      is_operator: false,
      capabilities: ['exam-result:read'],
    });
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7/slots/11/result').flush(
      resultFixture({
        external_results: [externalFixture()],
      }),
    );
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).not.toContain('Eigene Bewertung abgeben');
    expect(text).not.toContain('Vollständige Einzelbewertungen offenlegen');
    expect(text).not.toContain('Unbestätigt erfassen');
    expect(text).not.toContain('Unabhängig bestätigen');
    expect(text).not.toContain('Maschinenlesbarer Ergebnisexport');
  });

  it('offers four-eyes confirmation only to a different authorized member', () => {
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
    http
      .expectOne('/api/confirmed-plan-days/7/slots/11/result')
      .flush(resultFixture({ external_results: [externalFixture()] }));
    fixture.detectChanges();

    const button = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    ).find((item) => item.textContent?.trim() === 'Unabhängig bestätigen');
    expect(button).toBeTruthy();
    button?.click();
    const request = http.expectOne('/api/exam-results/41/external-results/12/confirm');
    expect(request.request.body).toEqual({ version: 4 });
    request.flush(
      resultFixture({
        version: 5,
        external_results: [externalFixture({ status: 'confirmed', confirmed_by_member_id: 2 })],
      }),
    );
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Externes Eingangsergebnis unabhängig bestätigt.',
    );
  });

  it('distinguishes an unbound result from a retryable loading failure', () => {
    fixture.detectChanges();
    http
      .expectOne('/api/confirmed-plan-days/7/slots/11/result')
      .flush({}, { status: 404, statusText: 'Not Found' });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'noch kein Bewertungsmodell gebunden',
    );

    const instance = fixture.componentInstance as unknown as { load(): void };
    instance.load();
    http
      .expectOne('/api/confirmed-plan-days/7/slots/11/result')
      .flush({}, { status: 500, statusText: 'Internal Server Error' });
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('konnte nicht geladen werden');
    const retry = Array.from(element.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.trim() === 'Erneut versuchen',
    );
    retry?.click();
    http.expectOne('/api/confirmed-plan-days/7/slots/11/result').flush(resultFixture());
  });

  it('renders calculations, immutable histories, corrections, and retention state', () => {
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 1,
      person_id: 1,
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
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7/slots/11/result').flush(richResultFixture());
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

    const instance = fixture.componentInstance as unknown as TestableExamResultComponent;
    expect(instance.stateLabel('communicated')).toBe('Mitgeteilt');
    expect(instance.stateLabel('future')).toBe('future');
    expect(instance.stateAppearance('determined')).toBe('positive');
    expect(instance.stateAppearance('calculation_ready')).toBe('warning');
    expect(instance.stateAppearance('incomplete')).toBe('neutral');
    expect(instance.hasConfirmedRecord(richResultFixture())).toBe(false);
  });

  it('executes every result action and surfaces a domain error', () => {
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 1,
      person_id: 1,
      committee_member_id: 1,
      is_operator: false,
      capabilities: ['exam-result:read'],
    });
    fixture.detectChanges();
    const initial = resultFixture({
      individual_assessments: [individualFixture()],
      external_results: [externalFixture({ recorded_by_member_id: 2 })],
    });
    http.expectOne('/api/confirmed-plan-days/7/slots/11/result').flush(initial);
    fixture.detectChanges();

    const instance = fixture.componentInstance as unknown as TestableExamResultComponent;
    const component = initial.model_version.rules.components[0];
    const criterion = component.criteria[0];
    instance.draftFor(component, criterion).changeReason = 'Erfassung berichtigen';
    instance.withdraw(component, criterion);
    http
      .expectOne('/api/exam-results/41/individual-assessments/21/withdraw')
      .flush(resultFixture());

    instance.disclose(component.key);
    http.expectOne('/api/exam-results/41/disclosures').flush(resultFixture());

    instance.componentPoints.set(component.key, '78');
    instance.componentReasons.set(component.key, 'Gemeinsamer Beschluss');
    instance.dissentMemberId = 2;
    instance.dissentStatement = 'Abweichende fachliche Würdigung';
    instance.determineComponent(component.key);
    const componentRequest = http.expectOne('/api/exam-results/41/committee-assessments');
    expect(componentRequest.request.body.dissent).toEqual([
      { member_id: 2, statement: 'Abweichende fachliche Würdigung' },
    ]);
    componentRequest.flush(resultFixture());

    instance.externalAreaKey = 'written';
    instance.externalPoints = '81';
    instance.externalGrade = 'gut';
    instance.externalAuthority = 'IHK Teststadt';
    instance.externalSource = 'Bescheid 17';
    instance.externalCorrectionReason = 'Übertragungsfehler berichtigt';
    instance.recordExternal();
    http.expectOne('/api/exam-results/41/external-results').flush(resultFixture());

    instance.confirmExternal(12);
    http.expectOne('/api/exam-results/41/external-results/12/confirm').flush(resultFixture());

    instance.determineResult();
    instance.determineResult();
    http.expectOne('/api/exam-results/41/determine').flush(resultFixture());

    instance.confirmRecord();
    http.expectOne('/api/exam-results/41/record-confirmations').flush(resultFixture());

    instance.correctionReason = 'Rechenweg berichtigen';
    instance.reopeningReference = 'Freigabe 18';
    instance.openCorrection();
    http.expectOne('/api/exam-results/41/corrections').flush(resultFixture());

    instance.communicationMethod = 'persönlich';
    instance.communicationAt = '2027-05-18T12:00';
    instance.externalDocumentReference = 'IHK-Schreiben 19';
    instance.communicate();
    http.expectOne('/api/exam-results/41/communications').flush(resultFixture());

    instance.retentionPeriodStart = '2027-06-01';
    instance.retentionUntil = '2042-06-01';
    instance.retentionLegalHold = true;
    instance.retentionHoldReason = 'Rechtsbehelf offen';
    instance.retentionReleaseReason = 'Später freigegeben';
    instance.saveRetention();
    http.expectOne('/api/exam-results/41/retention').flush(resultFixture());

    instance.determineResult();
    http
      .expectOne('/api/exam-results/41/determine')
      .flush({ error: { message: 'Versionskonflikt' } }, { status: 409, statusText: 'Conflict' });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Versionskonflikt');
  });
});

type TestableExamResultComponent = {
  draftFor(
    component: AssessmentComponent,
    criterion: AssessmentCriterion,
  ): {
    rawPoints: string;
    rationale: string;
    changeReason: string;
  };
  withdraw(component: AssessmentComponent, criterion: AssessmentCriterion): void;
  disclose(componentKey: string): void;
  determineComponent(componentKey: string): void;
  recordExternal(): void;
  confirmExternal(externalResultId: number): void;
  determineResult(): void;
  confirmRecord(): void;
  openCorrection(): void;
  communicate(): void;
  saveRetention(): void;
  stateLabel(value: string): string;
  stateAppearance(value: string): 'neutral' | 'positive' | 'warning';
  hasConfirmedRecord(result: ExamResult): boolean;
  componentPoints: Map<string, string>;
  componentReasons: Map<string, string>;
  dissentMemberId: number | null;
  dissentStatement: string;
  externalAreaKey: string;
  externalPoints: string;
  externalGrade: string;
  externalAuthority: string;
  externalSource: string;
  externalCorrectionReason: string;
  correctionReason: string;
  reopeningReference: string;
  communicationMethod: string;
  communicationAt: string;
  externalDocumentReference: string;
  retentionPeriodStart: string;
  retentionUntil: string;
  retentionLegalHold: boolean;
  retentionHoldReason: string;
  retentionReleaseReason: string;
};

function resultFixture(overrides: Partial<ExamResult> = {}): ExamResult {
  const component: AssessmentComponent = {
    key: 'documentation',
    label: 'Dokumentation',
    mode: 'independent',
    weight: '50',
    day_scoped: true,
    required_assessors: 2,
    max_deviation: '15',
    additional_assessor_on_deviation: true,
    criteria: [
      {
        key: 'quality',
        label: 'Fachliche Qualität',
        raw_min: '0',
        raw_max: '10',
        weight: '100',
      },
    ],
  };
  return {
    id: 41,
    round_candidate_id: 1,
    version: 4,
    state: 'incomplete',
    correction_open: false,
    legacy_status: null,
    candidate: {
      id: 1,
      first_name: 'Prüfling',
      last_name: 'Alpha',
      ihk_exam_number: 'TEST-2026-0001',
      specialization: 'application_development',
    },
    model_version: {
      id: 2,
      model_key: 'fiae-final-2026',
      version: 1,
      ihk: 'IHK Teststadt',
      occupation: 'Fachinformatiker/in',
      specialization: null,
      valid_from: '2026-01-01',
      valid_until: '2026-12-31',
      rules: {
        components: [component],
        external_areas: [{ key: 'written', label: 'Schriftlich', weight: '50', required: true }],
        rounding: {
          intermediate: { mode: 'none', digits: null },
          overall: { mode: 'half_up', digits: 0 },
          threshold_basis: 'unrounded',
        },
        grades: [{ label: 'bestanden', min_points: '0' }],
        passing: { overall_min: '50', component_minima: {}, external_minima: {} },
        quorum: { minimum_members: 3, majority: 'simple' },
      },
      retention_rule_reference: 'PrüfO § 31',
      retention_years: 15,
    },
    participants: [1, 2, 3],
    disclosures: [],
    individual_assessments: [],
    individual_assessment_counts: [],
    committee_assessments: [],
    external_results: [],
    current_calculation: null,
    determinations: [],
    current_determination: null,
    corrections: [],
    communications: [],
    retention: null,
    exports: [],
    permissions: {
      assess_own: true,
      disclose: true,
      determine_component: true,
      manage_external: true,
      determine_result: true,
      confirm_record: true,
      coordinate_correction: true,
      communicate: true,
      manage_retention: true,
    },
    _links: {
      machine_export: { href: '/api/exam-results/41/export.json' },
      human_export: { href: '/api/exam-results/41/export.txt' },
    },
    ...overrides,
  };
}

function externalFixture(
  overrides: Partial<ExamResult['external_results'][number]> = {},
): ExamResult['external_results'][number] {
  return {
    id: 12,
    area_key: 'written',
    revision: 1,
    points: '82',
    grade: 'gut',
    professional_status: 'bestanden',
    determining_authority: 'IHK Teststadt',
    source_reference: 'Bescheid TEST-2026-0001',
    status: 'unconfirmed',
    recorded_by_member_id: 1,
    confirmed_by_member_id: null,
    correction_reason: null,
    ...overrides,
  };
}

function individualFixture(): ExamResult['individual_assessments'][number] {
  return {
    id: 21,
    component_key: 'documentation',
    criterion_key: 'quality',
    assessor_member_id: 1,
    revision: 1,
    raw_points: '8',
    normalized_points: '80',
    rationale: 'Fachlich nachvollziehbar',
    status: 'submitted',
    change_reason: null,
    submitted_at: '2027-05-18T09:30:00Z',
  };
}

function richResultFixture(): ExamResult {
  const result = resultFixture({
    state: 'calculation_ready',
    correction_open: true,
    disclosures: [
      {
        component_key: 'presentation',
        disclosed_by_member_id: 1,
        disclosed_at: '2027-05-18T10:20:00Z',
      },
    ],
    individual_assessments: [individualFixture()],
    individual_assessment_counts: [{ component_key: 'documentation', draft: 0, submitted: 2 }],
    committee_assessments: [
      {
        id: 31,
        component_key: 'presentation',
        revision: 1,
        points: '75',
        rationale: 'Gemeinsame fachliche Würdigung',
        participant_member_ids: [1, 2, 3],
        vote: { yes: [1, 2], no: [3], abstain: [] },
        dissent: [{ member_id: 3, statement: 'Abweichende Gewichtung' }],
        status: 'current',
        determined_at: '2027-05-18T10:30:00Z',
      },
    ],
    external_results: [
      externalFixture({ recorded_by_member_id: 2 }),
      externalFixture({
        id: 13,
        revision: 2,
        points: '83',
        status: 'confirmed',
        recorded_by_member_id: 2,
        confirmed_by_member_id: 3,
        correction_reason: 'Externes Ergebnis berichtigt',
      }),
    ],
    current_calculation: {
      id: 51,
      version: 2,
      total_points: '76.25',
      grade: 'gut',
      passed: true,
      path: {
        inputs: [
          { kind: 'component', key: 'documentation', points: '70', weight: '50' },
          { kind: 'external', key: 'written', points: '82.5', weight: '50' },
        ],
        unrounded_total: '76.25',
        rounded_total: '76',
        threshold_basis: 'unrounded',
      },
    },
    corrections: [
      {
        id: 71,
        reason: 'Übertragungsfehler',
        status: 'open',
        reopening_reference: 'Freigabe 18',
      },
    ],
    communications: [
      {
        id: 81,
        method: 'persönlich',
        communicated_at: '2027-05-18T12:00:00Z',
        external_document_status: 'extern dokumentiert',
        external_document_reference: 'IHK-Schreiben 19',
        status: 'obsolete',
      },
    ],
    retention: {
      rule_reference: 'PrüfO § 31',
      period_start: '2027-06-01',
      retain_until: '2042-06-01',
      legal_hold: true,
      hold_reason: 'Rechtsbehelf offen',
    },
    exports: [
      {
        id: 91,
        result_determination_id: 61,
        export_kind: 'machine',
        status: 'superseded',
        generated_at: '2027-05-18T12:01:00Z',
      },
    ],
  });
  result.model_version.rules.components.push({
    key: 'presentation',
    label: 'Präsentation',
    mode: 'committee',
    weight: '50',
    day_scoped: true,
    required_assessors: 3,
    max_deviation: '100',
    additional_assessor_on_deviation: false,
    criteria: [
      {
        key: 'delivery',
        label: 'Darstellung',
        raw_min: '0',
        raw_max: '100',
        weight: '100',
      },
    ],
  });
  const determination: ExamResult['determinations'][number] = {
    id: 61,
    revision: 1,
    participant_member_ids: [1, 2, 3],
    vote: { yes: [1, 2, 3], no: [], abstain: [] },
    dissent: [],
    status: 'current',
    determined_at: '2027-05-18T11:30:00Z',
    confirmation_member_ids: [2, 3],
  };
  result.determinations = [determination];
  result.current_determination = determination;
  return result;
}
