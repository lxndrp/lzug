import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import type { ExamResult as ApiExamResult } from './execution.models';
import { HttpExamResultAdapter } from './http-exam-result.adapter';

describe('HttpExamResultAdapter', () => {
  let adapter: HttpExamResultAdapter;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), HttpExamResultAdapter],
    });
    adapter = TestBed.inject(HttpExamResultAdapter);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('maps API field names and export links into the feature model', () => {
    let result: unknown;
    adapter.get(7, 11).subscribe((value) => (result = value));
    const request = http.expectOne('/api/confirmed-plan-days/7/slots/11/result');
    expect(request.request.method).toBe('GET');
    request.flush(apiResult());

    expect(result).toMatchObject({
      roundCandidateId: 5,
      correctionOpen: false,
      modelVersion: {
        modelKey: 'standard',
        rules: {
          externalAreas: [{ key: 'practice', label: 'Praxis', weight: '0', required: false }],
          components: [
            {
              key: 'documentation',
              dayScoped: false,
              criteria: [{ key: 'clarity', rawMin: '0', rawMax: '100' }],
            },
          ],
          passing: {
            componentMinima: { technical_discussion: '50' },
            externalMinima: { written_exam: '40' },
          },
        },
      },
      individualAssessments: [{ componentKey: 'documentation', rawPoints: '82' }],
      currentCalculation: {
        totalPoints: '82',
        path: { unroundedTotal: '82', roundedTotal: '82' },
      },
      permissions: { assessOwn: true, determineResult: true },
      exportsLinks: {
        machine: '/api/exam-results/41/export.json',
        human: '/api/exam-results/41/export.txt',
      },
    });
  });

  it('serializes individual assessment and withdrawal commands at the HTTP boundary', () => {
    adapter
      .saveIndividualAssessment({
        resultId: 41,
        version: 3,
        componentKey: 'documentation',
        criterionKey: 'clarity',
        rawPoints: '82',
        rationale: '  Beobachtung  ',
        submitted: true,
        changeReason: '  Korrektur  ',
        dayRevisions: { '7': 4 },
      })
      .subscribe();
    const save = http.expectOne('/api/exam-results/41/individual-assessments');
    expect(save.request.method).toBe('POST');
    expect(save.request.body).toEqual({
      version: 3,
      component_key: 'documentation',
      criterion_key: 'clarity',
      raw_points: '82',
      rationale: 'Beobachtung',
      submitted: true,
      change_reason: 'Korrektur',
      day_revisions: { '7': 4 },
    });
    save.flush(apiResult());

    adapter.withdrawIndividualAssessment(41, 3, 21, '  Begründung  ', { '7': 4 }).subscribe();
    const withdraw = http.expectOne('/api/exam-results/41/individual-assessments/21/withdraw');
    expect(withdraw.request.body).toEqual({
      version: 3,
      reason: 'Begründung',
      day_revisions: { '7': 4 },
    });
    withdraw.flush(apiResult());
  });

  it('serializes disclosure, committee determination, and external-result commands', () => {
    adapter.discloseAssessments(41, 3, 'documentation', { '7': 4 }).subscribe();
    const disclosure = http.expectOne('/api/exam-results/41/disclosures');
    expect(disclosure.request.body).toEqual({
      version: 3,
      component_key: 'documentation',
      day_revisions: { '7': 4 },
    });
    disclosure.flush(apiResult());

    adapter
      .determineComponent({
        resultId: 41,
        version: 3,
        componentKey: 'documentation',
        points: '82',
        rationale: '  Gemeinsame Begründung  ',
        participants: [1, 2],
        dissent: [{ memberId: 2, statement: 'Abweichung' }],
        dayRevisions: { '7': 4 },
      })
      .subscribe();
    const committee = http.expectOne('/api/exam-results/41/committee-assessments');
    expect(committee.request.body).toEqual({
      version: 3,
      component_key: 'documentation',
      points: '82',
      rationale: 'Gemeinsame Begründung',
      participant_member_ids: [1, 2],
      vote: { yes: [1, 2], no: [], abstain: [] },
      dissent: [{ member_id: 2, statement: 'Abweichung' }],
      day_revisions: { '7': 4 },
    });
    committee.flush(apiResult());

    adapter
      .recordExternalResult({
        resultId: 41,
        version: 3,
        areaKey: 'practice',
        points: '78',
        grade: 'B',
        professionalStatus: 'verbindlich festgestellt',
        determiningAuthority: 'IHK',
        sourceReference: 'Bescheid',
        correctionReason: 'Korrektur',
        dayRevisions: { '7': 4 },
      })
      .subscribe();
    const external = http.expectOne('/api/exam-results/41/external-results');
    expect(external.request.body).toEqual({
      version: 3,
      area_key: 'practice',
      points: '78',
      grade: 'B',
      professional_status: 'verbindlich festgestellt',
      determining_authority: 'IHK',
      source_reference: 'Bescheid',
      correction_reason: 'Korrektur',
      day_revisions: { '7': 4 },
    });
    external.flush(apiResult());

    adapter.confirmExternalResult(41, 3, 12, { '7': 4 }).subscribe();
    const confirmation = http.expectOne('/api/exam-results/41/external-results/12/confirm');
    expect(confirmation.request.body).toEqual({ version: 3, day_revisions: { '7': 4 } });
    confirmation.flush(apiResult());
  });

  it('serializes determination, record confirmation, correction, communication, and retention', () => {
    adapter
      .determineExamResult({
        resultId: 41,
        version: 3,
        participants: [1, 2],
        dissent: [{ memberId: 2, statement: 'Abweichung' }],
        dayRevisions: { '7': 4 },
      })
      .subscribe();
    const determination = http.expectOne('/api/exam-results/41/determine');
    expect(determination.request.body).toEqual({
      version: 3,
      participant_member_ids: [1, 2],
      vote: { yes: [1, 2], no: [], abstain: [] },
      dissent: [{ member_id: 2, statement: 'Abweichung' }],
      day_revisions: { '7': 4 },
    });
    determination.flush(apiResult());

    adapter.confirmResultRecord(41, 3, { '7': 4 }).subscribe();
    const confirmation = http.expectOne('/api/exam-results/41/record-confirmations');
    expect(confirmation.request.body).toEqual({ version: 3, day_revisions: { '7': 4 } });
    confirmation.flush(apiResult());

    adapter.openResultCorrection(41, 3, '  Fehler  ', '  Referenz  ', { '7': 4 }).subscribe();
    const correction = http.expectOne('/api/exam-results/41/corrections');
    expect(correction.request.body).toEqual({
      version: 3,
      reason: 'Fehler',
      reopening_reference: 'Referenz',
      day_revisions: { '7': 4 },
    });
    correction.flush(apiResult());

    adapter
      .communicateExamResult(41, 3, '  persönlich  ', '2026-09-30T10:00', '  Dokument  ', {
        '7': 4,
      })
      .subscribe();
    const communication = http.expectOne('/api/exam-results/41/communications');
    expect(communication.request.body).toEqual({
      version: 3,
      method: 'persönlich',
      communicated_at: new Date('2026-09-30T10:00').toISOString(),
      external_document_status: 'extern dokumentiert',
      external_document_reference: 'Dokument',
      day_revisions: { '7': 4 },
    });
    communication.flush(apiResult());

    adapter
      .setExamResultRetention({
        resultId: 41,
        version: 3,
        periodStart: '2026-01-01',
        retainUntil: '2036-01-01',
        legalHold: true,
        holdReason: '  Prüfung  ',
        releaseReason: '  Freigabe  ',
        dayRevisions: { '7': 4 },
      })
      .subscribe();
    const retention = http.expectOne('/api/exam-results/41/retention');
    expect(retention.request.method).toBe('PUT');
    expect(retention.request.body).toEqual({
      version: 3,
      period_start: '2026-01-01',
      retain_until: '2036-01-01',
      legal_hold: true,
      hold_reason: '  Prüfung  ',
      release_reason: '  Freigabe  ',
      day_revisions: { '7': 4 },
    });
    retention.flush(apiResult());
  });
});

function apiResult(): ApiExamResult {
  return {
    id: 41,
    round_candidate_id: 5,
    day_revisions: { '7': 4 },
    version: 3,
    state: 'calculation_ready',
    correction_open: false,
    legacy_status: null,
    candidate: {
      id: 5,
      first_name: 'Ada',
      last_name: 'Beispiel',
      ihk_exam_number: '123',
      specialization: 'Anwendung',
    },
    model_version: {
      id: 2,
      model_key: 'standard',
      version: 1,
      ihk: 'IHK Beispiel',
      occupation: 'Fachinformatikerin',
      specialization: null,
      valid_from: '2026-01-01',
      valid_until: null,
      rules: {
        components: [
          {
            key: 'documentation',
            label: 'Dokumentation',
            mode: 'committee',
            weight: '100',
            day_scoped: false,
            required_assessors: 2,
            max_deviation: '20',
            additional_assessor_on_deviation: false,
            criteria: [
              { key: 'clarity', label: 'Klarheit', raw_min: '0', raw_max: '100', weight: '100' },
            ],
          },
        ],
        external_areas: [{ key: 'practice', label: 'Praxis', weight: '0', required: false }],
        rounding: {
          intermediate: { mode: 'none', digits: null },
          overall: { mode: 'none', digits: null },
          threshold_basis: 'unrounded',
        },
        grades: [{ label: 'Gut', min_points: '80' }],
        passing: {
          overall_min: '50',
          component_minima: { technical_discussion: '50' },
          external_minima: { written_exam: '40' },
        },
        quorum: { minimum_members: 2, majority: 'simple' },
      },
      retention_rule_reference: 'Prüfungsordnung',
      retention_years: 10,
    },
    participants: [1, 2],
    disclosures: [],
    individual_assessments: [
      {
        id: 21,
        component_key: 'documentation',
        criterion_key: 'clarity',
        assessor_member_id: 1,
        revision: 1,
        raw_points: '82',
        normalized_points: '82',
        rationale: 'Beobachtung',
        status: 'submitted',
        change_reason: null,
        submitted_at: '2026-09-30T12:00:00Z',
      },
    ],
    individual_assessment_counts: [{ component_key: 'documentation', draft: 0, submitted: 2 }],
    committee_assessments: [],
    external_results: [],
    current_calculation: {
      id: 91,
      version: 3,
      total_points: '82',
      grade: 'Gut',
      passed: true,
      path: {
        inputs: [{ kind: 'component', key: 'documentation', points: '82', weight: '100' }],
        unrounded_total: '82',
        rounded_total: '82',
        threshold_basis: 'unrounded',
      },
    },
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
  } as ApiExamResult;
}
