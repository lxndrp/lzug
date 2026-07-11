import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  BadgeModule,
  ButtonModule,
  CardModule,
  FormModule,
  GridModule,
  TableModule,
} from '@coreui/angular';

import {
  AvailabilityValue,
  CandidateExamDay,
  CommitteeMember,
  MasterData,
  MemberAvailability,
  PlanningBoard,
  PlanningSettings,
  RoundSummary,
} from '../api/api.models';

export type PlanningSettingsPayload = Omit<PlanningSettings, 'id' | 'exam_round_id'>;
export type CandidateExamDayPayload = Omit<CandidateExamDay, 'id' | 'exam_round_id'>;
export type AvailabilityPayload = Pick<
  MemberAvailability,
  'committee_member_id' | 'candidate_exam_day_id' | 'availability'
>;

@Component({
  selector: 'app-planning',
  imports: [BadgeModule, ButtonModule, CardModule, FormModule, FormsModule, GridModule, TableModule],
  templateUrl: './planning.component.html',
})
export class PlanningComponent implements OnChanges {
  @Input() summary: RoundSummary | null = null;
  @Input() board: PlanningBoard | null = null;
  @Input() masterData: MasterData | null = null;
  @Input() actionBusy = false;

  @Output() saveSettings = new EventEmitter<PlanningSettingsPayload>();
  @Output() createCandidateDay = new EventEmitter<CandidateExamDayPayload>();
  @Output() toggleCandidateDay = new EventEmitter<CandidateExamDay>();
  @Output() saveAvailability = new EventEmitter<AvailabilityPayload>();

  protected readonly draft: PlanningSettingsPayload = {
    calendar_week_from: '',
    calendar_week_to: '',
    exams_per_day: 6,
    max_exam_days_per_week: 3,
    lunch_break_enabled: 1,
    default_location_id: null,
    updated_by_member_id: 0,
  };
  protected readonly candidateDayDraft: CandidateExamDayPayload = {
    date: '',
    is_active: 1,
  };

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['summary'] || changes['board'] || changes['masterData']) {
      this.syncDraft();
    }
  }

  protected capacity(): number {
    const settings = this.summary?.settings;
    const activeDays = this.board?.candidateDays.filter((day) => day.is_active).length ?? 0;
    return activeDays * (settings?.exams_per_day ?? 0);
  }

  protected requiredSlots(): number {
    return this.summary?.counts.required_exam_slots ?? 0;
  }

  protected activeMembers(): CommitteeMember[] {
    return (this.masterData?.members ?? []).filter((member) => member.is_active);
  }

  protected availabilityOptions(): Array<{ value: AvailabilityValue; label: string }> {
    return [
      { value: 'full_day', label: 'Ganztägig' },
      { value: 'morning', label: 'Vormittag' },
      { value: 'afternoon', label: 'Nachmittag' },
      { value: 'unavailable', label: 'Nicht verfügbar' },
      { value: 'pending', label: 'Offen' },
    ];
  }

  protected availabilityFor(memberId: number, dayId: number): AvailabilityValue {
    return (
      this.board?.availabilities.find(
        (item) => item.committee_member_id === memberId && item.candidate_exam_day_id === dayId,
      )?.availability ?? 'pending'
    );
  }

  protected dateLabel(date: string): string {
    return new Intl.DateTimeFormat('de-DE', {
      weekday: 'short',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(new Date(`${date}T12:00:00Z`));
  }

  protected memberLabel(member: CommitteeMember): string {
    return `${member.first_name} ${member.last_name}`;
  }

  protected changeAvailability(
    member: CommitteeMember,
    day: CandidateExamDay,
    availability: AvailabilityValue,
  ): void {
    this.saveAvailability.emit({
      committee_member_id: member.id,
      candidate_exam_day_id: day.id,
      availability,
    });
  }

  protected submitCandidateDay(): void {
    if (!this.candidateDayDraft.date) {
      return;
    }
    this.createCandidateDay.emit({
      date: this.candidateDayDraft.date,
      is_active: this.candidateDayDraft.is_active ? 1 : 0,
    });
    this.candidateDayDraft.date = '';
    this.candidateDayDraft.is_active = 1;
  }

  protected submitSettings(): void {
    const updaterId = this.draft.updated_by_member_id || this.defaultUpdaterId();
    if (!updaterId || !this.draft.calendar_week_from || !this.draft.calendar_week_to) {
      return;
    }

    this.saveSettings.emit({
      ...this.draft,
      exams_per_day: Number(this.draft.exams_per_day) || 1,
      max_exam_days_per_week: Number(this.draft.max_exam_days_per_week) || 1,
      lunch_break_enabled: this.draft.lunch_break_enabled ? 1 : 0,
      default_location_id: this.draft.default_location_id ? Number(this.draft.default_location_id) : null,
      updated_by_member_id: updaterId,
    });
  }

  protected defaultUpdaterId(): number {
    return (
      this.masterData?.members.find((member) => member.committee_role === 'chair' && member.is_active)
        ?.id ??
      this.masterData?.members.find((member) => member.is_active)?.id ??
      0
    );
  }

  private syncDraft(): void {
    const settings = this.summary?.settings;
    this.draft.calendar_week_from = settings?.calendar_week_from ?? this.draft.calendar_week_from;
    this.draft.calendar_week_to = settings?.calendar_week_to ?? this.draft.calendar_week_to;
    this.draft.exams_per_day = settings?.exams_per_day ?? this.draft.exams_per_day;
    this.draft.max_exam_days_per_week =
      settings?.max_exam_days_per_week ?? this.draft.max_exam_days_per_week;
    this.draft.lunch_break_enabled =
      settings?.lunch_break_enabled ?? this.draft.lunch_break_enabled ?? 1;
    this.draft.default_location_id =
      settings?.default_location_id ?? this.board?.locations[0]?.id ?? null;
    this.draft.updated_by_member_id = settings?.updated_by_member_id ?? this.defaultUpdaterId();
  }
}
