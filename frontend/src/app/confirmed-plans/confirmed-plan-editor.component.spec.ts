import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideTaiga } from '@taiga-ui/core';
import { Subject, of, throwError } from 'rxjs';

import { ApplicationError } from '../application/application-error';
import {
  ConfirmedPlan,
  ConfirmedPlanRevision,
  EditablePlanningProposal,
  PlanningBoard,
} from '../api/api.models';
import { AuthService } from '../auth/auth.service';
import type { AuthSession } from '../auth/auth.service';
import { RuntimeExperienceService } from '../runtime/runtime-experience.service';
import { ConfirmedPlansWorkflowService } from './confirmed-plans-workflow.service';
import { ConfirmedPlanEditorComponent } from './confirmed-plan-editor.component';

describe('ConfirmedPlanEditorComponent', () => {
  let fixture: ComponentFixture<ConfirmedPlanEditorComponent>;
  let loads: Array<{
    roundId: number;
    subject: Subject<EditablePlanningProposal>;
    settled: boolean;
  }>;
  let saves: Array<Subject<EditablePlanningProposal>>;
  let workflow: {
    getEditableConfirmedPlan: ReturnType<typeof vi.fn>;
    saveEditableConfirmedPlan: ReturnType<typeof vi.fn>;
    getConfirmedPlanRevisions: ReturnType<typeof vi.fn>;
  };
  let runtime: { getDemoScenarios: ReturnType<typeof vi.fn> };
  let nextSaveError: Error | null;

  beforeEach(async () => {
    loads = [];
    saves = [];
    nextSaveError = null;
    workflow = {
      getEditableConfirmedPlan: vi.fn((roundId: number) => {
        const subject = new Subject<EditablePlanningProposal>();
        loads.push({ roundId, subject, settled: false });
        return subject;
      }),
      saveEditableConfirmedPlan: vi.fn(() => {
        if (nextSaveError) {
          const error = nextSaveError;
          nextSaveError = null;
          return throwError(() => error);
        }
        const subject = new Subject<EditablePlanningProposal>();
        saves.push(subject);
        return subject;
      }),
      getConfirmedPlanRevisions: vi.fn(() => of([] as ConfirmedPlanRevision[])),
    };
    runtime = { getDemoScenarios: vi.fn(() => of({ prepared_plan_change: null })) };

    await TestBed.configureTestingModule({
      imports: [ConfirmedPlanEditorComponent],
      providers: [
        provideTaiga({ scrollbars: 'native' }),
        {
          provide: AuthService,
          useValue: { session: signal<AuthSession | null>(null) },
        },
        { provide: ConfirmedPlansWorkflowService, useValue: workflow },
        { provide: RuntimeExperienceService, useValue: runtime },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(ConfirmedPlanEditorComponent);
    fixture.componentRef.setInput('roundId', 1);
    fixture.componentRef.setInput('plan', plan());
    fixture.componentRef.setInput('board', board());
  });

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
    expect(workflow.saveEditableConfirmedPlan).toHaveBeenCalledTimes(1);
    const [roundId, saved, changeReason] = workflow.saveEditableConfirmedPlan.mock.calls[0];
    expect(roundId).toBe(1);
    expect(changeReason).toBe('Reihenfolge nach Rücksprache korrigiert');
    expect(saved.exam_days[0].slots.map((slot: { id: number }) => slot.id)).toEqual([2, 1]);

    workflow.getConfirmedPlanRevisions.mockReturnValueOnce(
      of([
        {
          id: 1,
          previous_revision: 1,
          resulting_revision: 2,
          reason: changeReason,
          actor_member_id: 1,
          created_at: '2026-08-30T12:00:00Z',
          before: editablePlan(),
          after: { ...editablePlan(), revision: 2 },
        } satisfies ConfirmedPlanRevision,
      ]),
    );
    resolveSave({ ...editablePlan(), revision: 2 });
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
    resolveLoad(1, editablePlan());
    fixture.detectChanges();
    button(element, 'Termin 2 nach oben verschieben').click();
    const reason = element.querySelector<HTMLTextAreaElement>('#confirmedPlanChangeReason')!;
    reason.value = 'Aktuelle Planung anpassen';
    reason.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    const saveButton = button(element, 'Änderung mit Grund speichern');
    expect(saveButton.disabled).toBe(false);
    nextSaveError = new ApplicationError('conflict', 'conflict');
    saveButton.click();
    resolveLoad(1, { ...editablePlan(), revision: 3 });
    fixture.detectChanges();
    expect(element.textContent).toContain('Der Plan wurde inzwischen geändert.');
    expect(element.textContent).toContain('Revision 3');
  });

  it('ignores late responses from the previous round and preserves the current draft', () => {
    fixture.detectChanges();
    fixture.componentRef.setInput('roundId', 2);
    fixture.detectChanges();
    resolveLoad(2, { ...editablePlan(), round_id: 2 });
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    button(element, 'Termin 2 nach oben verschieben').click();
    const reason = element.querySelector<HTMLTextAreaElement>('#confirmedPlanChangeReason')!;
    reason.value = 'Entwurf der zweiten Runde';
    reason.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    rejectLoad(1, new Error('alte Runde nicht erreichbar'));
    fixture.detectChanges();
    expect(button(element, 'Änderung mit Grund speichern').disabled).toBe(false);
    expect(element.textContent).not.toContain('Der bestätigte Plan konnte nicht geladen werden.');

    button(element, 'Änderung mit Grund speichern').click();
    fixture.componentRef.setInput('roundId', 3);
    fixture.detectChanges();
    resolveLoad(3, { ...editablePlan(), round_id: 3 });
    resolveSave({ ...editablePlan(), round_id: 2, revision: 2 });
    fixture.detectChanges();

    expect(element.textContent).not.toContain(
      'Die Änderung wurde als neue Planrevision gespeichert.',
    );
    expect(button(element, 'Änderung mit Grund speichern').disabled).toBe(true);
  });

  it('ignores a late successful load from the previous round after the current draft changes', () => {
    fixture.detectChanges();
    fixture.componentRef.setInput('roundId', 2);
    fixture.detectChanges();
    resolveLoad(2, { ...editablePlan(), round_id: 2 });
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    button(element, 'Termin 2 nach oben verschieben').click();
    const reason = element.querySelector<HTMLTextAreaElement>('#confirmedPlanChangeReason')!;
    reason.value = 'Entwurf der zweiten Runde';
    reason.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    resolveLoad(1, { ...editablePlan(), revision: 7 });
    fixture.detectChanges();

    const firstCandidate = element.querySelector<HTMLSelectElement>(
      'select[aria-label="Prüfling für Termin 1"]',
    );
    expect(firstCandidate).not.toBeNull();
    expect(
      Array.from(firstCandidate!.options).find((option) => option.selected)?.textContent,
    ).toContain('Beta');
    expect(element.querySelector<HTMLTextAreaElement>('#confirmedPlanChangeReason')?.value).toBe(
      'Entwurf der zweiten Runde',
    );
    expect(button(element, 'Änderung mit Grund speichern').disabled).toBe(false);
  });

  it('hides the previous round editor while the newly selected round loads', () => {
    fixture.detectChanges();
    resolveLoad(1, editablePlan());
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Bestätigten Plan ändern');

    fixture.componentRef.setInput('roundId', 2);
    fixture.detectChanges();
    expect(element.textContent).toContain('Bearbeitbarer Plan wird geladen');
    expect(element.textContent).not.toContain('Bestätigten Plan ändern');
    expect(element.querySelector('.app-confirmed-editor-slots')).toBeNull();

    resolveLoad(2, { ...editablePlan(), round_id: 2 });
    fixture.detectChanges();
    expect(element.textContent).toContain('Bestätigten Plan ändern');
  });

  it('offers only the prepared atomic revision in the demo', () => {
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 1,
      person_id: 1,
      committee_member_id: 1,
      is_operator: false,
      demo_role: 'chair',
      capabilities: ['confirmed-plan:revise'],
    });
    runtime.getDemoScenarios.mockReturnValueOnce(
      of({
        prepared_plan_change: {
          round_id: 1,
          day_id: 1,
          source_location_id: 1,
          target_location_id: 2,
          assignment_id: 1,
          replacement_member_id: 2,
          reason: 'Synthetischer Ortswechsel mit gleichseitiger Ersatzbesetzung',
        },
      }),
    );
    fixture.detectChanges();
    resolveLoad(1, editablePlan());
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('ausschließlich die vorbereitete Ortsänderung');
    expect(element.querySelector<HTMLTextAreaElement>('#confirmedPlanChangeReason')?.readOnly).toBe(
      true,
    );
    expect(element.querySelector<HTMLFieldSetElement>('fieldset')?.disabled).toBe(true);
    const component = fixture.componentInstance as unknown as {
      controlsDisabled(day: ReturnType<typeof editablePlan>['exam_days'][number]): boolean;
    };
    expect(component.controlsDisabled(editablePlan().exam_days[0])).toBe(true);

    button(element, 'Änderung vorbereiten').click();
    fixture.detectChanges();
    button(element, 'Änderung mit Grund speichern').click();
    const [roundId, saved, reason] = workflow.saveEditableConfirmedPlan.mock.calls[0];
    expect(roundId).toBe(1);
    expect(reason).toBe('Synthetischer Ortswechsel mit gleichseitiger Ersatzbesetzung');
    expect(saved.exam_days[0].room_id).toBe(2);
    expect(saved.exam_days[0].location_id).toBe(2);
    expect(saved.exam_days[0].assignments[0].committee_member_id).toBe(2);
    expect(saved._links).toBeUndefined();
    resolveSave({ ...editablePlan(), revision: 2 });
    fixture.detectChanges();
    expect(element.textContent).toContain('Öffnen Sie die Demo-Szenarien');
  });

  function loadEditor(): void {
    fixture.detectChanges();
    resolveLoad(1, editablePlan());
    fixture.detectChanges();
  }

  function resolveLoad(roundId: number, value: ReturnType<typeof editablePlan>): void {
    const request = [...loads].reverse().find((item) => item.roundId === roundId && !item.settled);
    expect(request).toBeDefined();
    if (!request) throw new Error(`No pending confirmed-plan request for round ${roundId}`);
    request.settled = true;
    request.subject.next(value as EditablePlanningProposal);
    request.subject.complete();
  }

  function rejectLoad(roundId: number, error: Error): void {
    const request = [...loads].reverse().find((item) => item.roundId === roundId && !item.settled);
    expect(request).toBeDefined();
    if (!request) throw new Error(`No pending confirmed-plan request for round ${roundId}`);
    request.settled = true;
    request.subject.error(error);
  }

  function resolveSave(value: ReturnType<typeof editablePlan>): void {
    const request = saves.find((item) => !item.closed);
    expect(request).toBeDefined();
    if (!request) throw new Error('No pending confirmed-plan save request');
    request.next(value as EditablePlanningProposal);
    request.complete();
  }
});

function button(element: HTMLElement, label: string): HTMLButtonElement {
  const found = Array.from(element.querySelectorAll('button')).find(
    (item) => item.textContent?.includes(label) || item.getAttribute('aria-label') === label,
  );
  expect(found).toBeDefined();
  return found!;
}

function editablePlan(): EditablePlanningProposal {
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
    locations: [
      { id: 1, name: 'Prüfungszentrum', room: '101', city: 'Teststadt' },
      { id: 2, name: 'Ausweichort', room: '202', city: 'Teststadt' },
    ],
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
