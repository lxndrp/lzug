import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { HttpDemoScenariosAdapter } from './http-demo-scenarios.adapter';

describe('HttpDemoScenariosAdapter', () => {
  let adapter: HttpDemoScenariosAdapter;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    adapter = TestBed.inject(HttpDemoScenariosAdapter);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('maps the demo scenario response to transport-neutral feature models', () => {
    let actual: unknown;
    adapter.getOverview().subscribe((value) => (actual = value));

    const request = http.expectOne('/api/demo/scenarios');
    expect(request.request.method).toBe('GET');
    request.flush(apiOverview());

    expect(actual).toEqual({
      createdAt: '2026-09-02T10:00:00Z',
      currentRole: 'examiner',
      demoMatrixVersion: 'demo-paths-v8',
      expiresAt: '2026-09-02T11:00:00Z',
      locationContract: 'Reale Athener Anschriften sind synthetisch.',
      mode: 'demo',
      notices: ['Keine realen personenbezogenen Daten eingeben.'],
      preparedPlanChange: {
        assignmentId: 6,
        dayId: 2,
        reason: 'Synthetischer Ortswechsel',
        replacementMemberId: 6,
        roundId: 1,
        sourceLocationId: 1,
        targetLocationId: 2,
      },
      remainingSeconds: 3600,
      roles: [{ displayName: 'Peter Quince', name: 'examiner', task: 'Eigenen Ausfall melden' }],
      scenarios: [
        {
          completedSteps: 0,
          id: 'absence',
          nextAction: 'Eigenen Ausfall melden',
          nextRole: 'examiner',
          path: '/confirmed-plans/1/days/1',
          status: 'ready',
          title: 'Dringlicher Ausfall und Ersatz',
          totalSteps: 3,
        },
      ],
    });
  });

  it('resets the current scenarios without exposing the transport response', () => {
    let actual: unknown;
    adapter.reset().subscribe((value) => (actual = value));

    const request = http.expectOne('/api/demo/reset');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({});
    request.flush({ status: 'reset', role: 'chair', expires_at: '2026-09-02T11:00:00Z' });

    expect(actual).toBeUndefined();
  });
});

function apiOverview() {
  return {
    mode: 'demo' as const,
    demo_matrix_version: 'demo-paths-v8',
    current_role: 'examiner' as const,
    created_at: '2026-09-02T10:00:00Z',
    expires_at: '2026-09-02T11:00:00Z',
    remaining_seconds: 3600,
    roles: [
      { name: 'examiner' as const, display_name: 'Peter Quince', task: 'Eigenen Ausfall melden' },
    ],
    scenarios: [
      {
        id: 'absence' as const,
        title: 'Dringlicher Ausfall und Ersatz',
        status: 'ready' as const,
        completed_steps: 0,
        total_steps: 3,
        next_role: 'examiner' as const,
        next_action: 'Eigenen Ausfall melden',
        path: '/confirmed-plans/1/days/1',
      },
    ],
    prepared_plan_change: {
      round_id: 1,
      day_id: 2,
      source_location_id: 1,
      target_location_id: 2,
      assignment_id: 6,
      replacement_member_id: 6,
      reason: 'Synthetischer Ortswechsel',
    },
    notices: ['Keine realen personenbezogenen Daten eingeben.'],
    location_contract: 'Reale Athener Anschriften sind synthetisch.',
  };
}
