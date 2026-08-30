import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideTaiga } from '@taiga-ui/core';

import { ConfirmedPlanEditorComponent } from './confirmed-plan-editor.component';
import { ConfirmedPlan, PlanningBoard } from '../api/api.models';

describe('ConfirmedPlanEditorComponent', () => {
  let fixture: ComponentFixture<ConfirmedPlanEditorComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConfirmedPlanEditorComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTaiga({ scrollbars: 'native' }),
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(ConfirmedPlanEditorComponent);
    http = TestBed.inject(HttpTestingController);
    fixture.componentRef.setInput('roundId', 1);
    fixture.componentRef.setInput('plan', plan());
    fixture.componentRef.setInput('board', board());
  });

  afterEach(() => http.verify());

  it('requires a reason and persists an allowed reordered day as a revision', () => {
    loadEditor();
    const element = fixture.nativeElement as HTMLElement;

    expect(button(element, 'Änderung mit Grund speichern').disabled).toBe(true);
    button(element, 'Termin 2 nach oben verschieben').click();
    const reason = element.querySelector<HTMLTextAreaElement>('#confirmedPlanChangeReason');
    expect(reason).not.toBeNull();
    if (!reason) throw new Error('Change-reason input is missing');
    reason.value = 'Reihenfolge nach Rücksprache korrigiert';
    reason.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    button(element, 'Änderung mit Grund speichern').click();
    const request = http.expectOne('/api/exam-rounds/1/confirmed-plan');
    expect(request.request.method).toBe('PUT');
    expect(request.request.body.reason).toBe('Reihenfolge nach Rücksprache korrigiert');
    expect(request.request.body.exam_days[0].slots.map((slot: { id: number }) => slot.id)).toEqual([
      2, 1,
    ]);
    request.flush({ ...editablePlan(), revision: 2, latest_revision: { id: 1 } });
    http.expectOne('/api/exam-rounds/1/confirmed-plan/revisions').flush({
      items: [
        {
          id: 1,
          previous_revision: 1,
          resulting_revision: 2,
          reason: 'Reihenfolge nach Rücksprache korrigiert',
          actor_member_id: 1,
          created_at: '2026-08-30T12:00:00Z',
          before: editablePlan(),
          after: { ...editablePlan(), revision: 2 },
        },
      ],
      _links: {},
    });
    fixture.detectChanges();
    expect(element.textContent).toContain('Die Änderung wurde als neue Planrevision gespeichert.');
    expect(element.textContent).toContain('Revision 1 → 2');
  });

  it('shows a locked day read-only and reloads the aggregate after a conflict', () => {
    const locked = plan();
    locked.days[0].slots[0].actual_started_at = '2026-11-16T08:30:00+01:00';
    fixture.componentRef.setInput('plan', locked);
    loadEditor();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Dieser Prüfungstag ist gesperrt');
    expect(button(element, 'Termin 2 nach oben verschieben').disabled).toBe(true);

    fixture.componentRef.setInput('plan', plan());
    fixture.detectChanges();
    http.expectOne('/api/exam-rounds/1/confirmed-plan').flush(editablePlan());
    http.expectOne('/api/exam-rounds/1/confirmed-plan/revisions').flush({ items: [], _links: {} });
    button(element, 'Termin 2 nach oben verschieben').click();
    const reason = element.querySelector<HTMLTextAreaElement>('#confirmedPlanChangeReason')!;
    reason.value = 'Aktuelle Planung anpassen';
    reason.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    const saveButton = button(element, 'Änderung mit Grund speichern');
    expect(saveButton.disabled).toBe(false);
    saveButton.click();
    http
      .expectOne('/api/exam-rounds/1/confirmed-plan')
      .flush(
        { error: { code: 'confirmed_plan_conflict' } },
        { status: 409, statusText: 'Conflict' },
      );
    http.expectOne('/api/exam-rounds/1/confirmed-plan').flush({ ...editablePlan(), revision: 3 });
    http.expectOne('/api/exam-rounds/1/confirmed-plan/revisions').flush({ items: [], _links: {} });
    fixture.detectChanges();
    expect(element.textContent).toContain('Der Plan wurde inzwischen geändert.');
    expect(element.textContent).toContain('Revision 3');
  });

  function loadEditor(): void {
    fixture.detectChanges();
    http.expectOne('/api/exam-rounds/1/confirmed-plan').flush(editablePlan());
    http.expectOne('/api/exam-rounds/1/confirmed-plan/revisions').flush({ items: [], _links: {} });
    fixture.detectChanges();
  }
});

function button(element: HTMLElement, label: string): HTMLButtonElement {
  const found = Array.from(element.querySelectorAll('button')).find(
    (item) => item.textContent?.includes(label) || item.getAttribute('aria-label') === label,
  );
  expect(found).toBeDefined();
  return found!;
}

function editablePlan() {
  return {
    round_id: 1,
    revision: 1,
    exam_days: [
      {
        id: 1,
        candidate_exam_day_id: 1,
        date: '2026-11-16',
        location_id: 1,
        status: 'confirmed',
        slots: [
          {
            id: 1,
            round_candidate_id: 1,
            slot_type: 'regular',
            starts_at: '',
            ends_at: '',
            sequence_number: 1,
            status: 'confirmed',
          },
          {
            id: 2,
            round_candidate_id: 2,
            slot_type: 'regular',
            starts_at: '',
            ends_at: '',
            sequence_number: 2,
            status: 'confirmed',
          },
        ],
        assignments: [
          {
            id: 1,
            committee_member_id: 1,
            assignment_role: 'examiner',
            day_part: 'morning',
            fallback_status: null,
          },
          {
            id: 2,
            committee_member_id: 2,
            assignment_role: 'fallback',
            day_part: 'morning',
            fallback_status: 'confirmed',
          },
        ],
      },
    ],
    _links: {},
  };
}

function plan(): ConfirmedPlan {
  return {
    id: 1,
    name: 'Winter 2026/27',
    committee: { id: 1, name: 'Prüfungsausschuss Teststadt' },
    exam_half_year: { id: 1, season: 'winter', year: 2026, status: 'active' },
    days: [
      {
        id: 1,
        date: '2026-11-16',
        revision: 1,
        closure_status: 'open',
        location: { id: 1, name: 'Prüfungszentrum', room: '101', city: 'Teststadt' },
        slots: [
          {
            id: 1,
            starts_at: '',
            ends_at: '',
            sequence_number: 1,
            slot_type: 'regular',
            actual_started_at: null,
            execution_status: 'open',
            status_changed_at: '',
            actual_completed_at: null,
            status_reason: null,
            candidate_attendance: { status: 'open', arrived_at: null },
            candidate: {
              id: 1,
              first_name: 'Prüfling',
              last_name: 'Alpha',
              ihk_exam_number: 'TEST-1',
            },
          },
          {
            id: 2,
            starts_at: '',
            ends_at: '',
            sequence_number: 2,
            slot_type: 'regular',
            actual_started_at: null,
            execution_status: 'open',
            status_changed_at: '',
            actual_completed_at: null,
            status_reason: null,
            candidate_attendance: { status: 'open', arrived_at: null },
            candidate: {
              id: 2,
              first_name: 'Prüfling',
              last_name: 'Beta',
              ihk_exam_number: 'TEST-2',
            },
          },
        ],
        assignments: [],
        status_summary: { open: 2, running: 0, completed: 0, cancelled: 0, needs_follow_up: 0 },
      },
    ],
  };
}

function board(): PlanningBoard {
  return {
    days: [],
    members: [
      {
        id: 1,
        person_id: 1,
        committee_id: 1,
        first_name: 'Erika',
        last_name: 'Erste',
        member_status: 'ordinary',
        committee_role: 'member',
        representing_side: 'employer',
        email: 'erika@example.invalid',
        email_verified_at: null,
        mobile: null,
        is_active: 1,
      },
      {
        id: 2,
        person_id: 2,
        committee_id: 1,
        first_name: 'Fabian',
        last_name: 'Fallback',
        member_status: 'deputy',
        committee_role: 'member',
        representing_side: 'employee',
        email: 'fabian@example.invalid',
        email_verified_at: null,
        mobile: null,
        is_active: 1,
      },
    ],
    locations: [{ id: 1, name: 'Prüfungszentrum', room: '101', city: 'Teststadt' }],
    candidates: [
      {
        candidate: {
          id: 1,
          first_name: 'Prüfling',
          last_name: 'Alpha',
          ihk_exam_number: 'TEST-1',
          specialization: 'application_development',
          training_company: 'Testbetrieb',
        },
        roundCandidate: {
          id: 1,
          exam_round_id: 1,
          candidate_id: 1,
          attempt_number: 1,
          requires_mep: 0,
          is_active: 1,
        },
      },
      {
        candidate: {
          id: 2,
          first_name: 'Prüfling',
          last_name: 'Beta',
          ihk_exam_number: 'TEST-2',
          specialization: 'application_development',
          training_company: 'Testbetrieb',
        },
        roundCandidate: {
          id: 2,
          exam_round_id: 1,
          candidate_id: 2,
          attempt_number: 1,
          requires_mep: 0,
          is_active: 1,
        },
      },
    ],
    candidateDays: [],
    availabilities: [],
  };
}
