import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTaiga } from '@taiga-ui/core';

import {
  CandidateView,
  CommitteeMember,
  EditablePlanningProposal,
  Location,
} from '../api/api.models';
import { candidateViewsFixture, locationsFixture, membersFixture } from '../testing/fixtures';
import { PlanningProposalEditorComponent } from './planning-proposal-editor.component';

describe('PlanningProposalEditorComponent', () => {
  let fixture: ComponentFixture<PlanningProposalEditorComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PlanningProposalEditorComponent],
      providers: [provideTaiga({ scrollbars: 'native' })],
    }).compileComponents();

    fixture = TestBed.createComponent(PlanningProposalEditorComponent);
    fixture.componentRef.setInput('state', 'ready');
    fixture.componentRef.setInput('proposal', proposal());
    fixture.componentRef.setInput('locations', locationsFixture as Location[]);
    fixture.componentRef.setInput('candidates', candidateViewsFixture as CandidateView[]);
    fixture.componentRef.setInput('members', membersFixture as CommitteeMember[]);
    fixture.componentRef.setInput('candidateDays', [
      { id: 1, date: '2026-11-16', is_active: 1 },
      { id: 2, date: '2026-11-17', is_active: 1 },
    ]);
    fixture.detectChanges();
  });

  it('renders the proposal as an editable, labelled day list', () => {
    const element = fixture.nativeElement as HTMLElement;

    expect(element.textContent).toContain('Planungsvorschlag bearbeiten');
    expect(element.textContent).toContain('Mo., 16.11.2026');
    expect(element.textContent).toContain('Prüfling');
    expect(element.textContent).toContain('Prüfer und Fallback');
    expect(element.querySelector('[aria-label*="nach oben verschieben"]')).toBeTruthy();
    expect(element.querySelector('[aria-label*="auf einen anderen Tag verschieben"]')).toBeTruthy();
  });

  it('moves a slot to another active day and derives its new schedule locally', () => {
    const component = fixture.componentInstance as unknown as {
      draft: () => EditablePlanningProposal;
      moveSlotToDay: (
        day: EditablePlanningProposal['exam_days'][number],
        index: number,
        id: number,
      ) => void;
    };
    const firstDay = component.draft().exam_days[0];

    component.moveSlotToDay(firstDay, 0, 2);
    fixture.detectChanges();

    expect(component.draft().exam_days).toHaveLength(1);
    expect(component.draft().exam_days[0].candidate_exam_day_id).toBe(2);
    expect(component.draft().exam_days[0].slots[0].starts_at).toBe('2026-11-17 08:30:00');
    expect(component.draft().exam_days[0].slots[0].sequence_number).toBe(1);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Ungespeicherte Änderungen',
    );
  });

  it('does not enable saving for an empty local day', () => {
    fixture.componentRef.setInput('proposal', {
      ...proposal(),
      exam_days: [{ ...proposal().exam_days[0], slots: [] }],
    });
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain('mindestens ein Termin');
    expect(button(fixture.nativeElement as HTMLElement, 'Änderungen speichern')?.disabled).toBe(
      true,
    );
  });

  it('shows server validation beside the affected member', () => {
    fixture.componentRef.setInput('violations', [
      {
        code: 'member_unavailable',
        message: 'Mitglied ist am Vormittag nicht verfügbar.',
        day_id: 11,
        slot_id: null,
        member_id: 1,
      },
    ]);
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Mitglied ist am Vormittag nicht verfügbar.',
    );
    expect((fixture.nativeElement as HTMLElement).querySelector('[role="alert"]')).toBeTruthy();
  });
});

function button(element: HTMLElement, label: string): HTMLButtonElement | undefined {
  return Array.from(element.querySelectorAll('button')).find((item) =>
    item.textContent?.includes(label),
  );
}

function proposal(): EditablePlanningProposal {
  return {
    round_id: 1,
    revision: 3,
    exam_days: [
      {
        id: 11,
        candidate_exam_day_id: 1,
        date: '2026-11-16',
        location_id: 1,
        status: 'proposed',
        slots: [
          {
            id: 21,
            round_candidate_id: 1,
            slot_type: 'regular',
            starts_at: '2026-11-16 08:30:00',
            ends_at: '2026-11-16 09:30:00',
            sequence_number: 1,
            status: 'proposed',
          },
        ],
        assignments: [
          {
            id: 31,
            committee_member_id: 1,
            assignment_role: 'examiner',
            day_part: 'morning',
            fallback_status: null,
          },
        ],
      },
    ],
  };
}
