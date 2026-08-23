import {
  Component,
  EventEmitter,
  Input,
  OnChanges,
  Output,
  SimpleChanges,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TuiButton, TuiNotification, TuiTextfield } from '@taiga-ui/core';
import { TuiBadge, TuiSelect } from '@taiga-ui/kit';
import { TuiHeader } from '@taiga-ui/layout';

import {
  CandidateView,
  CommitteeMember,
  EditablePlanningProposal,
  Location,
  PlanningProposalAssignment,
  PlanningProposalDay,
  PlanningProposalSlot,
  PlanningValidationViolation,
} from '../api/api.models';
import { type SelectOption, selectStringify, selectValues } from '../select-options';

export type ProposalEditorState = 'idle' | 'loading' | 'ready' | 'saving' | 'error';

@Component({
  selector: 'app-planning-proposal-editor',
  imports: [FormsModule, TuiBadge, TuiButton, TuiHeader, TuiNotification, TuiSelect, TuiTextfield],
  templateUrl: './planning-proposal-editor.component.html',
  styleUrl: './planning-proposal-editor.component.css',
})
export class PlanningProposalEditorComponent implements OnChanges {
  @Input() proposal: EditablePlanningProposal | null = null;
  @Input() state: ProposalEditorState = 'idle';
  @Input() errorMessage: string | null = null;
  @Input() violations: PlanningValidationViolation[] = [];
  @Input() locations: Location[] = [];
  @Input() candidates: CandidateView[] = [];
  @Input() candidateDays: Array<{ id: number; date: string; is_active: number }> = [];
  @Input() members: CommitteeMember[] = [];
  @Input() maxSlotsPerDay = 6;
  @Input() lunchBreakEnabled = 1;
  @Input() disabled = false;

  @Output() load = new EventEmitter<void>();
  @Output() reload = new EventEmitter<void>();
  @Output() save = new EventEmitter<EditablePlanningProposal>();

  protected readonly draft = signal<EditablePlanningProposal | null>(null);
  protected readonly dirty = signal(false);

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['proposal'] && this.proposal) {
      this.draft.set(this.cloneProposal(this.proposal));
      this.dirty.set(false);
    }
  }

  protected isBusy(): boolean {
    return this.disabled || this.state === 'loading' || this.state === 'saving';
  }

  protected localErrors(): string[] {
    const proposal = this.draft();
    if (!proposal) return [];

    const errors: string[] = [];
    const seenCandidates = new Set<number>();
    for (const day of proposal.exam_days) {
      if (!day.slots.length) {
        errors.push(`${this.dateLabel(day.date)}: mindestens ein Termin ist erforderlich.`);
      }
      if (day.slots.length > this.maxSlotsPerDay) {
        errors.push(
          `${this.dateLabel(day.date)}: maximal ${this.maxSlotsPerDay} Termine pro Tag sind möglich.`,
        );
      }
      if (
        !this.locations.some(
          (location) => location.id === day.location_id && location.is_active !== 0,
        )
      ) {
        errors.push(`${this.dateLabel(day.date)}: Bitte wählen Sie einen aktiven Prüfungsort.`);
      }
      for (const slot of day.slots) {
        if (seenCandidates.has(slot.round_candidate_id)) {
          errors.push(`${this.dateLabel(day.date)}: Ein Prüfling ist mehrfach eingeplant.`);
        }
        seenCandidates.add(slot.round_candidate_id);
      }
    }
    return errors;
  }

  protected canSave(): boolean {
    return Boolean(this.draft()) && this.dirty() && !this.isBusy() && !this.localErrors().length;
  }

  protected dayError(day: PlanningProposalDay): string | null {
    const violation = this.violations.find((item) => item.day_id === day.id);
    return violation?.message ?? null;
  }

  protected slotError(slot: PlanningProposalSlot): string | null {
    const violation = this.violations.find((item) => item.slot_id === slot.id);
    return violation?.message ?? null;
  }

  protected memberError(day: PlanningProposalDay, memberId: number): string | null {
    const violation = this.violations.find(
      (item) => item.day_id === day.id && item.member_id === memberId,
    );
    return violation?.message ?? null;
  }

  protected candidateLabel(roundCandidateId: number): string {
    const view = this.candidates.find((item) => item.roundCandidate?.id === roundCandidateId);
    if (!view) return `Prüfling #${roundCandidateId}`;
    return `${view.candidate.first_name} ${view.candidate.last_name} · ${view.candidate.ihk_exam_number}`;
  }

  protected memberLabel(memberId: number): string {
    const member = this.members.find((item) => item.id === memberId);
    return member ? `${member.first_name} ${member.last_name}` : `Mitglied #${memberId}`;
  }

  protected dateLabel(date: string): string {
    return new Intl.DateTimeFormat('de-DE', {
      weekday: 'short',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(new Date(`${date}T12:00:00Z`));
  }

  protected slotLabel(slot: PlanningProposalSlot): string {
    return `${slot.starts_at.slice(-8, -3)}–${slot.ends_at.slice(-8, -3)}`;
  }

  protected assignmentLabel(assignment: PlanningProposalAssignment): string {
    const role = assignment.assignment_role === 'fallback' ? 'Fallback' : 'Prüfer';
    const part = assignment.day_part === 'full_day' ? 'ganztägig' : assignment.day_part;
    return `${role}, ${part}`;
  }

  protected locationLabel(location: Location): string {
    return `${location.name} · ${location.room}`;
  }

  protected activeLocations(): Location[] {
    return this.locations.filter((location) => location.is_active !== 0);
  }

  protected activeCandidateDays(): Array<{ id: number; date: string; is_active: number }> {
    return this.candidateDays.filter((day) => day.is_active !== 0);
  }

  protected candidateOptions(): readonly number[] {
    return selectValues(
      this.candidates
        .filter((item) => item.roundCandidate?.is_active !== 0 && item.roundCandidate)
        .map((item) => ({
          value: item.roundCandidate!.id,
          label: this.candidateLabel(item.roundCandidate!.id),
        })),
    );
  }

  protected candidateStringify = selectStringify(() => this.candidateSelectOptions());

  protected candidateSelectOptions(): readonly SelectOption<number>[] {
    return this.candidates
      .filter((item) => item.roundCandidate?.is_active !== 0 && item.roundCandidate)
      .map((item) => ({
        value: item.roundCandidate!.id,
        label: this.candidateLabel(item.roundCandidate!.id),
      }));
  }

  protected locationOptions(): readonly number[] {
    return selectValues(this.locationSelectOptions());
  }

  protected locationStringify = selectStringify(() => this.locationSelectOptions());

  protected locationSelectOptions(): readonly SelectOption<number>[] {
    return this.activeLocations().map((location) => ({
      value: location.id,
      label: this.locationLabel(location),
    }));
  }

  protected memberOptions(): readonly number[] {
    return selectValues(this.memberSelectOptions());
  }

  protected memberStringify = selectStringify(() => this.memberSelectOptions());

  protected memberSelectOptions(): readonly SelectOption<number>[] {
    return this.members
      .filter((member) => member.is_active !== 0)
      .map((member) => ({
        value: member.id,
        label: this.memberLabel(member.id),
      }));
  }

  protected updateDay(day: PlanningProposalDay, patch: Partial<PlanningProposalDay>): void {
    this.updateDraft((proposal) => {
      const target = proposal.exam_days.find(
        (item) => item.candidate_exam_day_id === day.candidate_exam_day_id,
      );
      if (target) Object.assign(target, patch);
    });
  }

  protected updateSlot(slot: PlanningProposalSlot, patch: Partial<PlanningProposalSlot>): void {
    const key = this.slotKey(slot);
    this.updateDraft((proposal) => {
      for (const day of proposal.exam_days) {
        const target = day.slots.find((item) => this.slotKey(item) === key);
        if (target) Object.assign(target, patch);
      }
    });
  }

  protected updateAssignment(
    assignment: PlanningProposalAssignment,
    patch: Partial<PlanningProposalAssignment>,
  ): void {
    const key = this.assignmentKey(assignment);
    this.updateDraft((proposal) => {
      for (const day of proposal.exam_days) {
        const target = day.assignments.find((item) => this.assignmentKey(item) === key);
        if (target) Object.assign(target, patch);
      }
    });
  }

  protected moveSlot(day: PlanningProposalDay, slotIndex: number, direction: -1 | 1): void {
    this.updateDraft((proposal) => {
      const index = proposal.exam_days.findIndex(
        (item) => item.candidate_exam_day_id === day.candidate_exam_day_id,
      );
      const targetIndex = slotIndex + direction;
      if (index < 0 || targetIndex < 0 || targetIndex >= day.slots.length) return;
      const targetDay = proposal.exam_days[index];
      [targetDay.slots[slotIndex], targetDay.slots[targetIndex]] = [
        targetDay.slots[targetIndex],
        targetDay.slots[slotIndex],
      ];
      this.normalizeSlots(targetDay);
    });
  }

  protected moveSlotToDay(
    day: PlanningProposalDay,
    slotIndex: number,
    candidateDayId: number,
  ): void {
    if (!candidateDayId) return;
    this.updateDraft((proposal) => {
      const sourceIndex = proposal.exam_days.findIndex(
        (item) => item.candidate_exam_day_id === day.candidate_exam_day_id,
      );
      if (sourceIndex < 0) return;
      const source = proposal.exam_days[sourceIndex];
      const candidateDay = this.activeCandidateDays().find((item) => item.id === candidateDayId);
      if (!candidateDay) return;
      let target = proposal.exam_days.find((item) => item.candidate_exam_day_id === candidateDayId);
      if (!target) {
        target = {
          id: null,
          candidate_exam_day_id: candidateDay.id,
          date: candidateDay.date,
          location_id: source.location_id,
          status: 'proposed',
          slots: [],
          assignments: [],
        };
        proposal.exam_days.push(target);
      }
      const [slot] = source.slots.splice(slotIndex, 1);
      if (!slot) return;
      target.slots.push(slot);
      this.normalizeSlots(source);
      this.normalizeSlots(target);
      if (!source.slots.length) proposal.exam_days.splice(sourceIndex, 1);
    });
  }

  protected addAssignment(day: PlanningProposalDay): void {
    const memberId = this.members.find((member) => member.is_active !== 0)?.id;
    if (!memberId) return;
    this.updateDraft((proposal) => {
      const target = proposal.exam_days.find(
        (item) => item.candidate_exam_day_id === day.candidate_exam_day_id,
      );
      target?.assignments.push({
        id: null,
        committee_member_id: memberId,
        assignment_role: 'examiner',
        day_part: target.slots.length > 4 ? 'afternoon' : 'morning',
        fallback_status: null,
      });
    });
  }

  protected removeAssignment(
    day: PlanningProposalDay,
    assignment: PlanningProposalAssignment,
  ): void {
    const key = this.assignmentKey(assignment);
    this.updateDraft((proposal) => {
      const target = proposal.exam_days.find(
        (item) => item.candidate_exam_day_id === day.candidate_exam_day_id,
      );
      const index = target?.assignments.findIndex((item) => this.assignmentKey(item) === key) ?? -1;
      if (index >= 0) target?.assignments.splice(index, 1);
    });
  }

  protected saveDraft(): void {
    const proposal = this.draft();
    if (proposal && this.canSave()) this.save.emit(this.cloneProposal(proposal));
  }

  private updateDraft(mutator: (proposal: EditablePlanningProposal) => void): void {
    const proposal = this.draft();
    if (!proposal) return;
    const copy = this.cloneProposal(proposal);
    mutator(copy);
    this.normalizeAllSlots(copy);
    this.draft.set(copy);
    this.dirty.set(true);
  }

  private normalizeAllSlots(proposal: EditablePlanningProposal): void {
    proposal.exam_days.sort((a, b) => a.date.localeCompare(b.date));
    for (const day of proposal.exam_days) this.normalizeSlots(day);
  }

  private normalizeSlots(day: PlanningProposalDay): void {
    let hour = 8;
    let minute = 30;
    day.slots.forEach((slot, index) => {
      if (this.lunchBreakEnabled !== 0 && hour === 12 && minute === 30) {
        hour = 13;
        minute = 30;
      }
      const starts = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
      hour += 1;
      const ends = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
      slot.sequence_number = index + 1;
      slot.starts_at = `${day.date} ${starts}:00`;
      slot.ends_at = `${day.date} ${ends}:00`;
    });
  }

  private cloneProposal(proposal: EditablePlanningProposal): EditablePlanningProposal {
    return JSON.parse(JSON.stringify(proposal)) as EditablePlanningProposal;
  }

  private slotKey(slot: PlanningProposalSlot): string {
    return slot.id === null
      ? `new:${slot.round_candidate_id}:${slot.sequence_number}`
      : `id:${slot.id}`;
  }

  private assignmentKey(assignment: PlanningProposalAssignment): string {
    return assignment.id === null
      ? `new:${assignment.committee_member_id}:${assignment.assignment_role}:${assignment.day_part}`
      : `id:${assignment.id}`;
  }
}
