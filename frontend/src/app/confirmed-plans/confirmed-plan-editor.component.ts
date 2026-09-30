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

import { ApplicationError } from '../application/application-error';
import { AuthService } from '../auth/auth.service';
import { RuntimeExperienceService } from '../runtime/runtime-experience.service';
import { ConfirmedPlansWorkflowService } from './confirmed-plans-workflow.service';
import type {
  ConfirmedPlan,
  ConfirmedPlanRevision,
  ConfirmedPlansBoard,
  EditableConfirmedPlan,
  EditableConfirmedPlanAssignment,
  EditableConfirmedPlanDay,
  EditableConfirmedPlanSlot,
  PreparedConfirmedPlanChange,
} from './confirmed-plans.models';

/** Lifecycle states exposed by the confirmed-plan editor. */
export type EditorState = 'loading' | 'ready' | 'saving' | 'error';

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
  private readonly confirmedPlans = inject(ConfirmedPlansWorkflowService);
  private readonly auth = inject(AuthService);
  private readonly runtimeExperience = inject(RuntimeExperienceService);

  @Input({ required: true }) roundId!: number;
  @Input({ required: true }) plan!: ConfirmedPlan;
  @Input() board: ConfirmedPlansBoard | null = null;

  protected readonly state = signal<EditorState>('loading');
  protected readonly draft = signal<EditableConfirmedPlan | null>(null);
  protected readonly revisions = signal<ConfirmedPlanRevision[]>([]);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly reason = signal('');
  protected readonly dirty = signal(false);
  protected readonly demoPreparedChange = signal<PreparedConfirmedPlanChange | null>(null);
  protected readonly isDemo = computed(() => this.auth.session()?.demo_role !== undefined);
  private readonly planView = signal<ConfirmedPlan | null>(null);
  private requestGeneration = 0;
  protected readonly lockedDayIds = computed(
    () =>
      new Set(
        (this.planView()?.days ?? [])
          .filter(
            (day) =>
              day.closureStatus !== 'open' ||
              day.slots.some(
                (slot) =>
                  slot.actualStartedAt !== null ||
                  slot.actualCompletedAt !== null ||
                  slot.executionStatus !== 'open',
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
    if (changes['roundId']) this.clearRoundState();
    if (changes['roundId'] || changes['plan']) this.load();
  }

  protected load(): void {
    if (!this.roundId) return;
    const generation = ++this.requestGeneration;
    const roundId = this.roundId;
    this.state.set('loading');
    this.errorMessage.set(null);
    this.confirmedPlans.getEditableConfirmedPlan(roundId).subscribe({
      next: (proposal) => {
        if (!this.isCurrentRequest(generation, roundId)) return;
        this.draft.set(this.clone(proposal));
        this.reason.set('');
        this.dirty.set(false);
        this.state.set('ready');
        this.loadDemoContract(generation, roundId);
        this.loadRevisions(generation, roundId);
      },
      error: () => {
        if (!this.isCurrentRequest(generation, roundId)) return;
        this.state.set('error');
        this.errorMessage.set('Der bestätigte Plan konnte nicht geladen werden.');
      },
    });
  }

  protected save(): void {
    const proposal = this.draft();
    if (!proposal || !this.canSave()) return;
    const generation = this.requestGeneration;
    const roundId = this.roundId;
    this.state.set('saving');
    this.errorMessage.set(null);
    this.confirmedPlans.saveEditableConfirmedPlan(roundId, proposal, this.reason()).subscribe({
      next: (saved) => {
        if (!this.isCurrentRequest(generation, roundId)) return;
        this.draft.set(this.clone(saved));
        this.reason.set('');
        this.dirty.set(false);
        this.state.set('ready');
        this.errorMessage.set(
          this.isDemo()
            ? 'Die Planrevision wurde gespeichert. Öffnen Sie die Demo-Szenarien für den nächsten Schritt.'
            : 'Die Änderung wurde als neue Planrevision gespeichert.',
        );
        this.loadRevisions(generation, roundId);
      },
      error: (error: ApplicationError) => {
        if (!this.isCurrentRequest(generation, roundId)) return;
        if (error.kind === 'conflict') {
          this.errorMessage.set(
            'Der Plan wurde inzwischen geändert. Die aktuelle Fassung wird neu geladen; Ihre lokalen Änderungen wurden nicht gespeichert.',
          );
          this.loadAfterConflict(generation, roundId);
          return;
        }
        this.errorMessage.set(
          error.message
            ? error.message
            : 'Die Änderung konnte nicht gespeichert werden. Prüfen Sie die Angaben und versuchen Sie es erneut.',
        );
        this.state.set('ready');
      },
    });
  }

  protected isLocked(day: EditableConfirmedPlanDay): boolean {
    return day.id === null || this.lockedDayIds().has(day.id);
  }

  protected controlsDisabled(day: EditableConfirmedPlanDay): boolean {
    return this.isLocked(day) || this.isDemo() || this.state() === 'saving';
  }

  protected prepareDemoChange(): void {
    const change = this.demoPreparedChange();
    const current = this.draft();
    if (!change || !current || this.dirty() || this.state() !== 'ready') return;
    const proposal = this.clone(current);
    const day = proposal.days.find((item) => item.id === change.dayId);
    const assignment = day?.assignments.find((item) => item.id === change.assignmentId);
    if (!day || !assignment) {
      this.errorMessage.set('Die vorbereitete Demo-Änderung passt nicht zum aktuellen Planstand.');
      return;
    }
    day.roomId = change.targetLocationId;
    day.locationId = change.targetLocationId;
    assignment.committeeMemberId = change.replacementMemberId;
    this.draft.set(proposal);
    this.reason.set(change.reason);
    this.dirty.set(true);
    this.errorMessage.set(null);
  }

  protected updateLocation(day: EditableConfirmedPlanDay, locationId: number): void {
    const roomId = Number(locationId);
    this.updateDay(day, { roomId, locationId: roomId });
  }

  protected updateSlot(
    day: EditableConfirmedPlanDay,
    slot: EditableConfirmedPlanSlot,
    patch: Partial<Pick<EditableConfirmedPlanSlot, 'roundCandidateId' | 'slotType'>>,
  ): void {
    if (this.isLocked(day) || this.isDemo()) return;
    this.update((proposal) => {
      const target = proposal.days.find((item) => item.id === day.id);
      const existing = target?.slots.find((item) => item.id === slot.id);
      if (existing) Object.assign(existing, patch);
    });
  }

  protected moveSlot(day: EditableConfirmedPlanDay, index: number, direction: -1 | 1): void {
    if (this.isLocked(day) || this.isDemo()) return;
    this.update((proposal) => {
      const target = proposal.days.find((item) => item.id === day.id);
      if (!target) return;
      const next = index + direction;
      if (next < 0 || next >= target.slots.length) return;
      [target.slots[index], target.slots[next]] = [target.slots[next], target.slots[index]];
      target.slots.forEach((slot, position) => (slot.sequenceNumber = position + 1));
    });
  }

  protected updateAssignment(
    day: EditableConfirmedPlanDay,
    assignment: EditableConfirmedPlanAssignment,
    patch: Partial<
      Pick<EditableConfirmedPlanAssignment, 'committeeMemberId' | 'assignmentRole' | 'dayPart'>
    >,
  ): void {
    if (this.isLocked(day) || this.isDemo()) return;
    this.update((proposal) => {
      const target = proposal.days.find((item) => item.id === day.id);
      const existing = target?.assignments.find((item) => item.id === assignment.id);
      if (existing) Object.assign(existing, patch);
    });
  }

  protected candidateLabel(id: number): string {
    const candidate = this.board?.candidates.find((item) => item.roundCandidateId === id);
    return candidate
      ? `${candidate.firstName} ${candidate.lastName} · ${candidate.examNumber}`
      : `Prüfling ${id}`;
  }

  protected memberLabel(id: number): string {
    const member = this.board?.members.find((item) => item.id === id);
    return member ? `${member.firstName} ${member.lastName}` : `Mitglied ${id}`;
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
    return `Revision ${revision.previousRevision} → ${revision.resultingRevision}`;
  }

  private loadAfterConflict(generation: number, roundId: number): void {
    this.state.set('loading');
    this.confirmedPlans.getEditableConfirmedPlan(roundId).subscribe({
      next: (proposal) => {
        if (!this.isCurrentRequest(generation, roundId)) return;
        this.draft.set(this.clone(proposal));
        this.reason.set('');
        this.dirty.set(false);
        this.state.set('ready');
        this.loadDemoContract(generation, roundId);
        this.loadRevisions(generation, roundId);
      },
      error: () => {
        if (!this.isCurrentRequest(generation, roundId)) return;
        this.state.set('error');
        this.errorMessage.set(
          'Der neue Planstand konnte nicht geladen werden. Bitte laden Sie die Seite erneut.',
        );
      },
    });
  }

  private loadRevisions(generation: number, roundId: number): void {
    this.confirmedPlans.getConfirmedPlanRevisions(roundId).subscribe({
      next: (revisions) => {
        if (this.isCurrentRequest(generation, roundId)) this.revisions.set(revisions);
      },
      error: () => {
        if (this.isCurrentRequest(generation, roundId)) this.revisions.set([]);
      },
    });
  }

  private loadDemoContract(generation: number, roundId: number): void {
    if (!this.isDemo()) {
      this.demoPreparedChange.set(null);
      return;
    }
    this.runtimeExperience.getDemoScenarios().subscribe({
      next: (overview) => {
        if (this.isCurrentRequest(generation, roundId)) {
          const change = overview.prepared_plan_change;
          this.demoPreparedChange.set(
            change
              ? {
                  roundId: change.round_id,
                  dayId: change.day_id,
                  sourceLocationId: change.source_location_id,
                  targetLocationId: change.target_location_id,
                  assignmentId: change.assignment_id,
                  replacementMemberId: change.replacement_member_id,
                  reason: change.reason,
                }
              : null,
          );
        }
      },
      error: () => {
        if (!this.isCurrentRequest(generation, roundId)) return;
        this.demoPreparedChange.set(null);
        this.errorMessage.set('Die vorbereitete Demo-Änderung konnte nicht geladen werden.');
      },
    });
  }

  private isCurrentRequest(generation: number, roundId: number): boolean {
    return generation === this.requestGeneration && roundId === this.roundId;
  }

  private clearRoundState(): void {
    this.draft.set(null);
    this.revisions.set([]);
    this.errorMessage.set(null);
    this.reason.set('');
    this.dirty.set(false);
    this.demoPreparedChange.set(null);
  }

  private updateDay(day: EditableConfirmedPlanDay, patch: Partial<EditableConfirmedPlanDay>): void {
    if (this.isLocked(day) || this.isDemo()) return;
    this.update((proposal) => {
      const target = proposal.days.find((item) => item.id === day.id);
      if (target) Object.assign(target, patch);
    });
  }

  private update(mutator: (proposal: EditableConfirmedPlan) => void): void {
    const current = this.draft();
    if (!current) return;
    const copy = this.clone(current);
    mutator(copy);
    this.draft.set(copy);
    this.dirty.set(true);
  }

  private clone(proposal: EditableConfirmedPlan): EditableConfirmedPlan {
    return structuredClone(proposal);
  }
}
