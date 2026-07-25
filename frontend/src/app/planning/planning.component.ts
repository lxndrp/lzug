import {
  Component,
  EventEmitter,
  Input,
  OnChanges,
  OnDestroy,
  Output,
  SimpleChanges,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TuiButton, TuiCheckbox, TuiInput, TuiNotification, TuiTextfield } from '@taiga-ui/core';
import { TuiDay, TuiTime } from '@taiga-ui/cdk/date-time';
import { TuiBadge, TuiInputDate, TuiInputDateTime, TuiSelect } from '@taiga-ui/kit';
import { TuiTable } from '@taiga-ui/addon-table';
import { TuiForm, TuiHeader } from '@taiga-ui/layout';

import {
  AvailabilityValue,
  CandidateDayGenerationResult,
  CandidateExamDay,
  CommitteeMember,
  ExamRound,
  ExamRoundUpdate,
  MasterData,
  MemberAvailability,
  PlanningBoard,
  PlanningSettings,
  RoundSummary,
} from '../api/api.models';
import { appIcons } from '../app-icons';
import { AppIconDirective } from '../app-icon.directive';

export type PlanningSettingsPayload = Omit<PlanningSettings, 'id' | 'exam_round_id'>;
export type CandidateExamDayPayload = Omit<CandidateExamDay, 'id' | 'exam_round_id'>;
export type RoundUpdatePayload = ExamRoundUpdate;
export type AvailabilityPayload = Pick<
  MemberAvailability,
  'committee_member_id' | 'candidate_exam_day_id' | 'availability'
>;
/** Transient UI state for one optimistic availability update. */
export type AvailabilityCellState = {
  status: 'saving' | 'saved' | 'error';
  previous: AvailabilityValue;
};

/**
 * Presents and edits one planning round, including optimistic availability
 * changes. The parent owns network effects and calls the acknowledgement
 * methods below to settle each cell state.
 */
@Component({
  selector: 'app-planning',
  imports: [
    AppIconDirective,
    FormsModule,
    TuiButton,
    TuiBadge,
    TuiCheckbox,
    TuiForm,
    TuiHeader,
    TuiInputDate,
    TuiInputDateTime,
    TuiInput,
    TuiSelect,
    TuiTable,
    TuiTextfield,
    TuiNotification,
  ],
  templateUrl: './planning.component.html',
})
export class PlanningComponent implements OnChanges, OnDestroy {
  protected readonly icons = appIcons;
  @Input() round: ExamRound | null = null;
  @Input() summary: RoundSummary | null = null;
  @Input() board: PlanningBoard | null = null;
  @Input() masterData: MasterData | null = null;
  @Input() actionBusy = false;
  @Input() candidateDayGenerationResult: CandidateDayGenerationResult | null = null;

  @Output() saveSettings = new EventEmitter<PlanningSettingsPayload>();
  @Output() saveRound = new EventEmitter<RoundUpdatePayload>();
  @Output() createCandidateDay = new EventEmitter<CandidateExamDayPayload>();
  @Output() generateCandidateDays = new EventEmitter<PlanningSettingsPayload>();
  @Output() toggleCandidateDay = new EventEmitter<CandidateExamDay>();
  @Output() saveAvailability = new EventEmitter<AvailabilityPayload>();

  protected readonly draft: PlanningSettingsPayload = {
    calendar_week_from: '',
    calendar_week_to: '',
    exams_per_day: 6,
    max_exam_days_per_week: 3,
    lunch_break_enabled: 1,
    exclude_public_holidays: 0,
    holiday_subdivision_code: null,
    default_location_id: null,
    updated_by_member_id: 0,
  };
  protected readonly roundDraft = {
    name: '',
    availability_deadline: '',
    availability_reminder_at: '',
  };
  protected readonly candidateDayDraft: CandidateExamDayPayload = {
    date: '',
    is_active: 1,
  };
  protected candidateDayDateValue: TuiDay | null = null;
  protected availabilityDeadlineValue: readonly [TuiDay, TuiTime | null] | null = null;
  protected availabilityReminderValue: readonly [TuiDay, TuiTime | null] | null = null;
  protected readonly availabilityCellStates = signal<Record<string, AvailabilityCellState>>({});
  private readonly availabilityOverrides = signal<Record<string, AvailabilityValue>>({});
  private readonly savedStateTimers = new Map<string, ReturnType<typeof setTimeout>>();
  protected readonly federalStates = [
    { code: 'DE-BW', name: 'Baden-Württemberg' },
    { code: 'DE-BY', name: 'Bayern' },
    { code: 'DE-BE', name: 'Berlin' },
    { code: 'DE-BB', name: 'Brandenburg' },
    { code: 'DE-HB', name: 'Bremen' },
    { code: 'DE-HH', name: 'Hamburg' },
    { code: 'DE-HE', name: 'Hessen' },
    { code: 'DE-MV', name: 'Mecklenburg-Vorpommern' },
    { code: 'DE-NI', name: 'Niedersachsen' },
    { code: 'DE-NW', name: 'Nordrhein-Westfalen' },
    { code: 'DE-RP', name: 'Rheinland-Pfalz' },
    { code: 'DE-SL', name: 'Saarland' },
    { code: 'DE-SN', name: 'Sachsen' },
    { code: 'DE-ST', name: 'Sachsen-Anhalt' },
    { code: 'DE-SH', name: 'Schleswig-Holstein' },
    { code: 'DE-TH', name: 'Thüringen' },
  ] as const;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['round']) {
      this.syncRoundDraft();
    }
    if (changes['summary'] || changes['board'] || changes['masterData']) {
      this.syncDraft();
      this.syncSelectOptions();
    }
  }

  ngOnDestroy(): void {
    this.savedStateTimers.forEach((timer) => clearTimeout(timer));
    this.savedStateTimers.clear();
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

  protected readonly availabilityOptionValues: AvailabilityValue[] = [
    'full_day',
    'morning',
    'afternoon',
    'unavailable',
    'pending',
  ];
  protected readonly availabilityOptionLabels = [
    'Ganztägig',
    'Vormittag',
    'Nachmittag',
    'Nicht verfügbar',
    'Offen',
  ];
  protected readonly holidaySubdivisionOptions: Array<string | null> = [
    null,
    ...this.federalStates.map((state) => state.code),
  ];
  protected readonly holidaySubdivisionLabels = [
    'Bundesland auswählen',
    ...this.federalStates.map((state) => state.name),
  ];
  protected defaultLocationOptions: Array<number | null> = [null];
  protected defaultLocationLabels = ['Kein Standardort'];
  protected updatedByMemberOptions: number[] = [];
  protected updatedByMemberLabels: string[] = [];

  protected availabilityFor(memberId: number, dayId: number): AvailabilityValue {
    const key = this.availabilityCellKey(memberId, dayId);
    const overrides = this.availabilityOverrides();
    if (key in overrides) {
      return overrides[key];
    }
    return this.persistedAvailabilityFor(memberId, dayId);
  }

  protected availabilityCellState(
    memberId: number,
    dayId: number,
  ): AvailabilityCellState | undefined {
    return this.availabilityCellStates()[this.availabilityCellKey(memberId, dayId)];
  }

  protected availabilityStatusId(memberId: number, dayId: number): string {
    return `availability-status-${memberId}-${dayId}`;
  }

  protected isAvailabilitySaving(memberId: number, dayId: number): boolean {
    return this.availabilityCellState(memberId, dayId)?.status === 'saving';
  }

  private persistedAvailabilityFor(memberId: number, dayId: number): AvailabilityValue {
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

  protected memberSideLabel(member: CommitteeMember): string {
    const labels: Record<string, string> = {
      employer: 'Arbeitgeber',
      employee: 'Arbeitnehmer',
      school: 'Schule',
    };
    return labels[member.representing_side] ?? member.representing_side;
  }

  /**
   * Optimistically expose a new availability value and request persistence.
   *
   * The previous value is retained per cell, allowing ``markAvailabilityError``
   * to revert only the failed request rather than resetting unrelated edits.
   */
  protected changeAvailability(
    member: CommitteeMember,
    day: CandidateExamDay,
    availability: AvailabilityValue,
  ): void {
    const key = this.availabilityCellKey(member.id, day.id);
    const previous = this.availabilityFor(member.id, day.id);
    if (availability === previous) {
      return;
    }

    this.clearSavedStateTimer(key);
    this.availabilityOverrides.update((overrides) => ({ ...overrides, [key]: availability }));
    this.availabilityCellStates.update((states) => ({
      ...states,
      [key]: { status: 'saving', previous },
    }));
    this.saveAvailability.emit({
      committee_member_id: member.id,
      candidate_exam_day_id: day.id,
      availability,
    });
  }

  /**
   * Settle an optimistic cell as saved, then remove its transient feedback.
   *
   * Replacing an existing timer prevents an earlier acknowledgement from
   * clearing feedback for a later change to the same cell.
   */
  markAvailabilitySaved(payload: AvailabilityPayload): void {
    const key = this.availabilityCellKey(
      payload.committee_member_id,
      payload.candidate_exam_day_id,
    );
    const state = this.availabilityCellStates()[key];
    if (!state) {
      return;
    }

    this.availabilityCellStates.update((states) => ({
      ...states,
      [key]: { ...state, status: 'saved' },
    }));
    this.clearSavedStateTimer(key);
    this.savedStateTimers.set(
      key,
      setTimeout(() => {
        this.removeAvailabilityCellEntry(key);
        this.savedStateTimers.delete(key);
      }, 1800),
    );
  }

  /** Revert a failed optimistic cell to the value recorded before its request. */
  markAvailabilityError(payload: AvailabilityPayload): void {
    const key = this.availabilityCellKey(
      payload.committee_member_id,
      payload.candidate_exam_day_id,
    );
    const state = this.availabilityCellStates()[key];
    if (!state) {
      return;
    }

    this.clearSavedStateTimer(key);
    this.availabilityOverrides.update((overrides) => ({
      ...overrides,
      [key]: state.previous,
    }));
    this.availabilityCellStates.update((states) => ({
      ...states,
      [key]: { ...state, status: 'error' },
    }));
  }

  protected submitCandidateDay(): void {
    if (!this.candidateDayDraft.date) {
      return;
    }
    this.createCandidateDay.emit({
      date: this.candidateDayDraft.date,
      is_active: this.candidateDayDraft.is_active ? 1 : 0,
    });
  }

  protected candidateDayValue(): TuiDay | null {
    return this.candidateDayDraft.date ? TuiDay.jsonParse(this.candidateDayDraft.date) : null;
  }

  protected setCandidateDayValue(value: TuiDay | null): void {
    this.candidateDayDateValue = value;
    this.candidateDayDraft.date = value?.toJSON() ?? '';
  }

  protected roundDateTimeValue(value: string): readonly [TuiDay, TuiTime | null] | null {
    if (!value) {
      return null;
    }

    const [date, time = '00:00'] = value.split('T');
    return [TuiDay.jsonParse(date), TuiTime.fromString(time)];
  }

  protected setRoundDateTimeValue(
    field: 'availability_deadline' | 'availability_reminder_at',
    value: readonly [TuiDay, TuiTime | null] | null,
  ): void {
    if (field === 'availability_deadline') {
      this.availabilityDeadlineValue = value;
    } else {
      this.availabilityReminderValue = value;
    }
    this.roundDraft[field] = value
      ? `${value[0].toJSON()}T${value[1]?.toString('HH:MM') ?? '00:00'}`
      : '';
  }

  resetCandidateDayDraft(): void {
    this.candidateDayDraft.date = '';
    this.candidateDayDraft.is_active = 1;
    this.candidateDayDateValue = null;
  }

  protected submitSettings(): void {
    const payload = this.settingsPayload();
    if (payload) {
      this.saveSettings.emit(payload);
    }
  }

  protected submitRound(): void {
    if (!this.roundDraft.name.trim()) {
      return;
    }
    this.saveRound.emit({
      name: this.roundDraft.name.trim(),
      availability_deadline: this.toApiDateTime(this.roundDraft.availability_deadline),
      availability_reminder_at: this.toApiDateTime(this.roundDraft.availability_reminder_at),
    });
  }

  protected requestCandidateDayGeneration(): void {
    const payload = this.settingsPayload();
    if (payload) {
      this.generateCandidateDays.emit(payload);
    }
  }

  protected canGenerateCandidateDays(): boolean {
    return this.settingsPayload() !== null;
  }

  private settingsPayload(): PlanningSettingsPayload | null {
    const updaterId = this.draft.updated_by_member_id || this.defaultUpdaterId();
    if (
      !updaterId ||
      !this.draft.calendar_week_from ||
      !this.draft.calendar_week_to ||
      (this.draft.exclude_public_holidays && !this.draft.holiday_subdivision_code)
    ) {
      return null;
    }

    return {
      ...this.draft,
      exams_per_day: Number(this.draft.exams_per_day) || 1,
      max_exam_days_per_week: Number(this.draft.max_exam_days_per_week) || 1,
      lunch_break_enabled: this.draft.lunch_break_enabled ? 1 : 0,
      exclude_public_holidays: this.draft.exclude_public_holidays ? 1 : 0,
      holiday_subdivision_code: this.draft.holiday_subdivision_code || null,
      default_location_id: this.draft.default_location_id
        ? Number(this.draft.default_location_id)
        : null,
      updated_by_member_id: updaterId,
    };
  }

  protected defaultUpdaterId(): number {
    return (
      this.masterData?.members.find(
        (member) => member.committee_role === 'chair' && member.is_active,
      )?.id ??
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
    this.draft.exclude_public_holidays =
      settings?.exclude_public_holidays ?? this.draft.exclude_public_holidays ?? 0;
    this.draft.holiday_subdivision_code =
      settings?.holiday_subdivision_code ?? this.draft.holiday_subdivision_code ?? null;
    this.draft.default_location_id =
      settings?.default_location_id ??
      this.board?.locations.find((location) => location.is_active !== 0)?.id ??
      null;
    this.draft.updated_by_member_id = settings?.updated_by_member_id ?? this.defaultUpdaterId();
  }

  private syncSelectOptions(): void {
    const locations = (this.board?.locations ?? []).filter((location) => location.is_active !== 0);
    this.defaultLocationOptions = [null, ...locations.map((location) => location.id)];
    this.defaultLocationLabels = [
      'Kein Standardort',
      ...locations.map((location) => `${location.name} · ${location.room}`),
    ];

    const members = this.masterData?.members ?? [];
    this.updatedByMemberOptions = members.map((member) => member.id);
    this.updatedByMemberLabels = members.map(
      (member) => `${member.first_name} ${member.last_name}`,
    );
  }

  private syncRoundDraft(): void {
    if (!this.round) {
      return;
    }
    this.roundDraft.name = this.round.name;
    this.roundDraft.availability_deadline = this.toDateTimeLocal(this.round.availability_deadline);
    this.roundDraft.availability_reminder_at = this.toDateTimeLocal(
      this.round.availability_reminder_at,
    );
    this.availabilityDeadlineValue = this.roundDateTimeValue(this.roundDraft.availability_deadline);
    this.availabilityReminderValue = this.roundDateTimeValue(
      this.roundDraft.availability_reminder_at,
    );
  }

  protected dateTimeLabel(value?: string | null): string {
    if (!value) {
      return '–';
    }
    return new Intl.DateTimeFormat('de-DE', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value.replace(' ', 'T')));
  }

  private toDateTimeLocal(value?: string | null): string {
    return value ? value.replace(' ', 'T').slice(0, 16) : '';
  }

  private toApiDateTime(value: string): string | null {
    return value ? `${value.replace('T', ' ')}:00` : null;
  }

  private availabilityCellKey(memberId: number, dayId: number): string {
    return `${memberId}:${dayId}`;
  }

  private clearSavedStateTimer(key: string): void {
    const timer = this.savedStateTimers.get(key);
    if (timer) {
      clearTimeout(timer);
      this.savedStateTimers.delete(key);
    }
  }

  private removeAvailabilityCellEntry(key: string): void {
    this.availabilityOverrides.update((overrides) => this.withoutKey(overrides, key));
    this.availabilityCellStates.update((states) => this.withoutKey(states, key));
  }

  private withoutKey<T>(record: Record<string, T>, key: string): Record<string, T> {
    const copy = { ...record };
    delete copy[key];
    return copy;
  }
}
