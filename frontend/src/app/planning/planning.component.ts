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
  EditablePlanningProposal,
  ExamRound,
  ExamRoundUpdate,
  Location,
  MasterData,
  MemberAvailability,
  PlanningBoard,
  PlanningResult,
  PlanningSettings,
  PlanningValidationViolation,
  RoundSummary,
} from '../api/api.models';
import { appIcons } from '../app-icons';
import { AppIconDirective } from '../app-icon.directive';
import { type SelectOption, selectStringify, selectValues } from '../select-options';
import {
  PlanningProposalEditorComponent,
  ProposalEditorState,
} from './planning-proposal-editor.component';

export type PlanningSettingsPayload = Omit<
  PlanningSettings,
  'id' | 'exam_round_id' | 'updated_by_member_id'
>;
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

export type WizardStep = 'period' | 'conditions' | 'request' | 'responses' | 'confirmation';

export type WizardStepDefinition = {
  id: WizardStep;
  label: string;
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
    PlanningProposalEditorComponent,
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
  @Input() planningResult: PlanningResult | null = null;
  @Input() planningProposal: EditablePlanningProposal | null = null;
  @Input() proposalEditorState: ProposalEditorState = 'idle';
  @Input() proposalEditorError: string | null = null;
  @Input() proposalEditorViolations: PlanningValidationViolation[] = [];

  @Output() saveSettings = new EventEmitter<PlanningSettingsPayload>();
  @Output() saveRound = new EventEmitter<RoundUpdatePayload>();
  @Output() requestAvailabilities = new EventEmitter<RoundUpdatePayload>();
  @Output() createCandidateDay = new EventEmitter<CandidateExamDayPayload>();
  @Output() generateCandidateDays = new EventEmitter<PlanningSettingsPayload>();
  @Output() toggleCandidateDay = new EventEmitter<CandidateExamDay>();
  @Output() saveAvailability = new EventEmitter<AvailabilityPayload>();
  @Output() generateProposal = new EventEmitter<void>();
  @Output() confirmPlan = new EventEmitter<void>();
  @Output() loadPlanningProposal = new EventEmitter<void>();
  @Output() reloadPlanningProposal = new EventEmitter<void>();
  @Output() savePlanningProposal = new EventEmitter<EditablePlanningProposal>();
  @Output() cancel = new EventEmitter<void>();

  protected readonly currentStep = signal<WizardStep>('period');
  protected readonly minReachableStepIndex = signal<number>(0);
  protected readonly maxReachableStepIndex = signal<number>(0);
  protected readonly stepErrors = signal<Partial<Record<WizardStep, string>>>({});
  protected readonly wizardSteps: WizardStepDefinition[] = [
    { id: 'period', label: 'Zeitraum' },
    { id: 'conditions', label: 'Rahmenbedingungen' },
    { id: 'request', label: 'Verfügbarkeitsanfrage' },
    { id: 'responses', label: 'Rückmeldungen' },
    { id: 'confirmation', label: 'Bestätigung' },
  ];

  protected readonly draft: PlanningSettingsPayload = {
    calendar_week_from: '',
    calendar_week_to: '',
    exams_per_day: 6,
    max_exam_days_per_week: 3,
    lunch_break_enabled: 1,
    exclude_public_holidays: 0,
    holiday_subdivision_code: null,
    default_location_id: null,
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
  private workflowKey = '';
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
    if (changes['round'] || changes['summary'] || changes['board']) {
      this.syncWorkflowState();
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

  protected selectStep(step: WizardStep): void {
    this.currentStep.set(step);
  }

  protected currentStepIndex(): number {
    return this.wizardSteps.findIndex((item) => item.id === this.currentStep());
  }

  protected nextStep(): void {
    const step = this.currentStep();
    if (!['period', 'conditions'].includes(step)) {
      return;
    }
    const error = this.validateStep(step);
    if (error) {
      this.stepErrors.update((errors) => ({ ...errors, [step]: error }));
      return;
    }
    this.stepErrors.update((errors) => ({ ...errors, [step]: undefined }));
    const index = this.wizardSteps.findIndex((item) => item.id === step);
    const next = this.wizardSteps[index + 1];
    if (next) {
      this.currentStep.set(next.id);
      if (index + 1 > this.maxReachableStepIndex()) {
        this.maxReachableStepIndex.set(index + 1);
      }
    }
  }

  protected previousStep(): void {
    const index = this.currentStepIndex();
    const previous = this.wizardSteps[index - 1];
    if (previous) {
      this.currentStep.set(previous.id);
    }
  }

  protected stepError(step: WizardStep): string | undefined {
    return this.stepErrors()[step];
  }

  protected availabilityResponseCount(): number {
    const activeMemberIds = new Set(this.activeMembers().map((m) => m.id));
    const activeDayIds = new Set(
      (this.board?.candidateDays ?? []).filter((d) => d.is_active).map((d) => d.id),
    );
    return (this.board?.availabilities ?? []).filter(
      (item) =>
        item.availability !== 'pending' &&
        activeMemberIds.has(item.committee_member_id) &&
        activeDayIds.has(item.candidate_exam_day_id),
    ).length;
  }

  protected activeCandidateDayCount(): number {
    return (this.board?.candidateDays ?? []).filter((day) => day.is_active).length;
  }

  protected requiredSlots(): number {
    return this.summary?.counts.required_exam_slots ?? 0;
  }

  protected activeMembers(): CommitteeMember[] {
    return (this.masterData?.members ?? []).filter((member) => member.is_active);
  }

  protected proposalLocations(): Location[] {
    return (this.masterData?.locations ?? []).filter(
      (location) => location.committee_id === this.round?.committee_id,
    );
  }

  protected readonly availabilitySelectOptions: readonly SelectOption<AvailabilityValue>[] = [
    { value: 'full_day', label: 'Ganztägig' },
    { value: 'morning', label: 'Vormittag' },
    { value: 'afternoon', label: 'Nachmittag' },
    { value: 'unavailable', label: 'Nicht verfügbar' },
    { value: 'pending', label: 'Offen' },
  ];
  protected readonly availabilityOptionValues = selectValues(this.availabilitySelectOptions);
  protected readonly availabilityStringify = selectStringify(() => this.availabilitySelectOptions);
  protected readonly holidaySubdivisionSelectOptions: readonly SelectOption<string>[] =
    this.federalStates.map((state) => ({ value: state.code, label: state.name }));
  protected readonly holidaySubdivisionOptions = selectValues(this.holidaySubdivisionSelectOptions);
  protected readonly holidaySubdivisionStringify = selectStringify(
    () => this.holidaySubdivisionSelectOptions,
  );
  protected defaultLocationSelectOptions: readonly SelectOption<number>[] = [];
  protected readonly defaultLocationStringify = selectStringify(
    () => this.defaultLocationSelectOptions,
  );

  protected defaultLocationOptions(): readonly number[] {
    return selectValues(this.defaultLocationSelectOptions);
  }

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
    const payload = this.roundPayload();
    if (!payload) {
      return;
    }
    this.saveRound.emit(payload);
  }

  protected requestAvailabilityCoordination(): void {
    const error = this.validateStep('request');
    if (error) {
      this.stepErrors.update((errors) => ({ ...errors, request: error }));
      return;
    }
    const payload = this.roundPayload();
    if (payload) {
      this.stepErrors.update((errors) => ({ ...errors, request: undefined }));
      this.requestAvailabilities.emit(payload);
    }
  }

  protected requestCandidateDayGeneration(): void {
    const payload = this.settingsPayload();
    if (payload) {
      this.generateCandidateDays.emit(payload);
    }
  }

  protected generatePlanningProposal(): void {
    const error = this.validateStep('responses');
    if (error) {
      this.stepErrors.update((errors) => ({ ...errors, responses: error }));
      return;
    }
    this.stepErrors.update((errors) => ({ ...errors, responses: undefined }));
    this.generateProposal.emit();
  }

  protected canGenerateCandidateDays(): boolean {
    return this.settingsPayload() !== null;
  }

  protected canConfirmProposal(): boolean {
    return (
      this.round?.status === 'plan_proposed' && this.planningResult?.validation?.passed !== false
    );
  }

  protected workflowStageLabel(): string {
    const labels: Record<string, string> = {
      draft: 'Entwurf',
      availability_requested: 'In Abstimmung',
      availability_closed: 'In Abstimmung',
      plan_proposed: 'Planung',
      in_progress: 'Planung',
      plan_confirmed: 'Bestätigt',
    };
    return labels[this.round?.status ?? ''] ?? 'Terminorganisation';
  }

  protected workflowStageDescription(): string {
    const descriptions: Record<string, string> = {
      draft: 'Zeitraum und Rahmenbedingungen bearbeiten',
      availability_requested: 'Verfügbarkeiten und Rückmeldungen koordinieren',
      availability_closed: 'Rückmeldungen prüfen und Planung vorbereiten',
      plan_proposed: 'Vorschlag prüfen und verbindlich bestätigen',
      in_progress: 'Planung fortsetzen',
    };
    return descriptions[this.round?.status ?? ''] ?? 'Bearbeitungsstand wird geladen';
  }

  private validateStep(step: WizardStep): string | null {
    if (step === 'period' && !this.settingsPayload()) {
      return 'Bitte geben Sie Zeitraum und bei Feiertagsauswahl das Bundesland an.';
    }
    if (step === 'conditions' && this.activeCandidateDayCount() === 0) {
      return 'Bitte berechnen oder erfassen Sie mindestens einen aktiven möglichen Prüfungstag.';
    }
    if (
      step === 'request' &&
      (!this.roundDraft.name.trim() || !this.roundDraft.availability_deadline)
    ) {
      return 'Bitte geben Sie Bezeichnung und Rückmeldefrist für die Verfügbarkeitsanfrage an.';
    }
    if (step === 'responses' && this.activeMembers().length === 0) {
      return 'Für Rückmeldungen muss mindestens ein aktives Ausschussmitglied vorhanden sein.';
    }
    return null;
  }

  private settingsPayload(): PlanningSettingsPayload | null {
    if (
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
    };
  }

  private roundPayload(): RoundUpdatePayload | null {
    if (!this.roundDraft.name.trim()) {
      return null;
    }
    return {
      name: this.roundDraft.name.trim(),
      availability_deadline: this.toApiDateTime(this.roundDraft.availability_deadline),
      availability_reminder_at: this.toApiDateTime(this.roundDraft.availability_reminder_at),
    };
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
  }

  private syncSelectOptions(): void {
    const locations = (this.board?.locations ?? []).filter((location) => location.is_active !== 0);
    this.defaultLocationSelectOptions = locations.map((location) => ({
      value: location.id,
      label: `${location.name} · ${location.room}`,
    }));
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

  private syncWorkflowState(): void {
    if (!this.round) {
      return;
    }
    const key = `${this.round.id}:${this.round.status}`;
    if (key === this.workflowKey) {
      return;
    }
    this.workflowKey = key;

    if (['availability_requested', 'availability_closed'].includes(this.round.status)) {
      this.minReachableStepIndex.set(2);
      this.maxReachableStepIndex.set(3);
      this.currentStep.set('responses');
      return;
    }
    if (['plan_proposed', 'in_progress'].includes(this.round.status)) {
      this.minReachableStepIndex.set(4);
      this.maxReachableStepIndex.set(4);
      this.currentStep.set('confirmation');
      return;
    }

    this.minReachableStepIndex.set(0);
    const hasSettings = !!this.summary?.settings;
    const hasActiveDay = this.activeCandidateDayCount() > 0;
    this.maxReachableStepIndex.set(hasActiveDay ? 2 : hasSettings ? 1 : 0);
    this.currentStep.set('period');
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
