import {
  Component,
  Input,
  OnChanges,
  SimpleChanges,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TuiButton, TuiNotification } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';

import {
  ConfirmedPlan,
  ConfirmedPlanRevision,
  EditablePlanningProposal,
  PlanningBoard,
  PlanningProposalAssignment,
  PlanningProposalDay,
  PlanningProposalSlot,
} from '../api/api.models';
import { PlanningApiService } from '../api/planning-api.service';

type EditorState = 'loading' | 'ready' | 'saving' | 'error';

/**
 * Edits the revisioned confirmed-plan aggregate.  The server remains
 * authoritative for all locks and domain validation; this view makes the
 * currently known lock state and optimistic conflict handling understandable.
 */
@Component({
  selector: 'app-confirmed-plan-editor',
  imports: [FormsModule, TuiBadge, TuiButton, TuiNotification],
  templateUrl: './confirmed-plan-editor.component.html',
  styleUrl: './confirmed-plan-editor.component.css',
})
export class ConfirmedPlanEditorComponent implements OnChanges {
  private readonly api = inject(PlanningApiService);

  @Input({ required: true }) roundId!: number;
  @Input({ required: true }) plan!: ConfirmedPlan;
  @Input() board: PlanningBoard | null = null;

  protected readonly state = signal<EditorState>('loading');
  protected readonly draft = signal<EditablePlanningProposal | null>(null);
  protected readonly revisions = signal<ConfirmedPlanRevision[]>([]);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly reason = signal('');
  protected readonly dirty = signal(false);
  private readonly planView = signal<ConfirmedPlan | null>(null);
  protected readonly lockedDayIds = computed(
    () =>
      new Set(
        (this.planView()?.days ?? [])
          .filter(
            (day) =>
              day.closure_status !== 'open' ||
              day.slots.some(
                (slot) =>
                  slot.actual_started_at !== null ||
                  slot.actual_completed_at !== null ||
                  slot.execution_status !== 'open',
              ),
          )
          .map((day) => day.id),
      ),
  );
  protected readonly canSave = computed(
    () =>
      this.state() === 'ready' &&
      this.dirty() &&
      this.reason().trim().length > 0 &&
      this.draft() !== null,
  );

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['plan']) this.planView.set(this.plan);
    if (changes['roundId'] || changes['plan']) this.load();
  }

  protected load(): void {
    if (!this.roundId) return;
    this.state.set('loading');
    this.errorMessage.set(null);
    this.api.getEditableConfirmedPlan(this.roundId).subscribe({
      next: (proposal) => {
        this.draft.set(this.clone(proposal));
        this.reason.set('');
        this.dirty.set(false);
        this.state.set('ready');
        this.loadRevisions();
      },
      error: () => {
        this.state.set('error');
        this.errorMessage.set('Der bestätigte Plan konnte nicht geladen werden.');
      },
    });
  }

  protected save(): void {
    const proposal = this.draft();
    if (!proposal || !this.canSave()) return;
    this.state.set('saving');
    this.errorMessage.set(null);
    this.api.saveEditableConfirmedPlan(this.roundId, proposal, this.reason()).subscribe({
      next: (saved) => {
        this.draft.set(this.clone(saved));
        this.reason.set('');
        this.dirty.set(false);
        this.state.set('ready');
        this.errorMessage.set('Die Änderung wurde als neue Planrevision gespeichert.');
        this.loadRevisions();
      },
      error: (error: { status?: number; error?: { error?: { message?: string } | string } }) => {
        if (error.status === 409) {
          this.errorMessage.set(
            'Der Plan wurde inzwischen geändert. Die aktuelle Fassung wird neu geladen; Ihre lokalen Änderungen wurden nicht gespeichert.',
          );
          this.loadAfterConflict();
          return;
        }
        const detail = error.error?.error;
        this.errorMessage.set(
          typeof detail === 'object' && detail?.message
            ? detail.message
            : 'Die Änderung konnte nicht gespeichert werden. Prüfen Sie die Angaben und versuchen Sie es erneut.',
        );
        this.state.set('ready');
      },
    });
  }

  protected isLocked(day: PlanningProposalDay): boolean {
    return day.id === null || this.lockedDayIds().has(day.id);
  }

  protected updateLocation(day: PlanningProposalDay, locationId: number): void {
    this.updateDay(day, { location_id: Number(locationId) });
  }

  protected updateSlot(
    day: PlanningProposalDay,
    slot: PlanningProposalSlot,
    patch: Partial<Pick<PlanningProposalSlot, 'round_candidate_id' | 'slot_type'>>,
  ): void {
    if (this.isLocked(day)) return;
    this.update((proposal) => {
      const target = proposal.exam_days.find((item) => item.id === day.id);
      const existing = target?.slots.find((item) => item.id === slot.id);
      if (existing) Object.assign(existing, patch);
    });
  }

  protected moveSlot(day: PlanningProposalDay, index: number, direction: -1 | 1): void {
    if (this.isLocked(day)) return;
    this.update((proposal) => {
      const target = proposal.exam_days.find((item) => item.id === day.id);
      if (!target) return;
      const next = index + direction;
      if (next < 0 || next >= target.slots.length) return;
      [target.slots[index], target.slots[next]] = [target.slots[next], target.slots[index]];
      target.slots.forEach((slot, position) => (slot.sequence_number = position + 1));
    });
  }

  protected updateAssignment(
    day: PlanningProposalDay,
    assignment: PlanningProposalAssignment,
    patch: Partial<
      Pick<PlanningProposalAssignment, 'committee_member_id' | 'assignment_role' | 'day_part'>
    >,
  ): void {
    if (this.isLocked(day)) return;
    this.update((proposal) => {
      const target = proposal.exam_days.find((item) => item.id === day.id);
      const existing = target?.assignments.find((item) => item.id === assignment.id);
      if (existing) Object.assign(existing, patch);
    });
  }

  protected candidateLabel(id: number): string {
    const candidate = this.board?.candidates.find(
      (item) => item.roundCandidate?.id === id,
    )?.candidate;
    return candidate
      ? `${candidate.first_name} ${candidate.last_name} · ${candidate.ihk_exam_number}`
      : `Prüfling ${id}`;
  }

  protected memberLabel(id: number): string {
    const member = this.board?.members.find((item) => item.id === id);
    return member ? `${member.first_name} ${member.last_name}` : `Mitglied ${id}`;
  }

  protected locationLabel(id: number): string {
    const location = this.board?.locations.find((item) => item.id === id);
    return location ? `${location.name} · ${location.room}, ${location.city}` : `Prüfungsort ${id}`;
  }

  protected dateLabel(date: string): string {
    return new Intl.DateTimeFormat('de-DE', { dateStyle: 'full' }).format(
      new Date(`${date}T12:00:00`),
    );
  }

  protected revisionLabel(revision: ConfirmedPlanRevision): string {
    return `Revision ${revision.previous_revision} → ${revision.resulting_revision}`;
  }

  private loadAfterConflict(): void {
    this.state.set('loading');
    this.api.getEditableConfirmedPlan(this.roundId).subscribe({
      next: (proposal) => {
        this.draft.set(this.clone(proposal));
        this.reason.set('');
        this.dirty.set(false);
        this.state.set('ready');
        this.loadRevisions();
      },
      error: () => {
        this.state.set('error');
        this.errorMessage.set(
          'Der neue Planstand konnte nicht geladen werden. Bitte laden Sie die Seite erneut.',
        );
      },
    });
  }

  private loadRevisions(): void {
    this.api.getConfirmedPlanRevisions(this.roundId).subscribe({
      next: (revisions) => this.revisions.set(revisions),
      error: () => this.revisions.set([]),
    });
  }

  private updateDay(day: PlanningProposalDay, patch: Partial<PlanningProposalDay>): void {
    if (this.isLocked(day)) return;
    this.update((proposal) => {
      const target = proposal.exam_days.find((item) => item.id === day.id);
      if (target) Object.assign(target, patch);
    });
  }

  private update(mutator: (proposal: EditablePlanningProposal) => void): void {
    const current = this.draft();
    if (!current) return;
    const copy = this.clone(current);
    mutator(copy);
    this.draft.set(copy);
    this.dirty.set(true);
  }

  private clone(proposal: EditablePlanningProposal): EditablePlanningProposal {
    return structuredClone(proposal);
  }
}
