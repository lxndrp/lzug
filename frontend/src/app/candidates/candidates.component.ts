import {
  ChangeDetectorRef,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  Output,
  ViewChild,
  inject,
  signal,
} from '@angular/core';
import {
  AbstractControl,
  FormControl,
  FormGroup,
  FormsModule,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { TuiButton, TuiCheckbox, TuiInput, TuiTextfield } from '@taiga-ui/core';
import { TuiBadge, TuiSelect } from '@taiga-ui/kit';
import { TuiTable } from '@taiga-ui/addon-table';
import { TuiForm, TuiHeader } from '@taiga-ui/layout';

import {
  Candidate,
  CandidateCommitteeAssignment,
  CandidateView,
  ExamRound,
  MasterData,
} from '../api/api.models';
import type {
  CandidateCreate,
  CandidateUpdate as GeneratedCandidateUpdate,
} from '../api/generated/types.gen';
import { appIcons } from '../app-icons';
import { AppIconDirective } from '../app-icon.directive';
import { type SelectOption, selectLabel, selectStringify, selectValues } from '../select-options';

export type CandidatePayload = CandidateCreate & {
  exam_round_id?: number;
  assignment_change_reason?: string | null;
};
export type CandidateUpdate = {
  id: number;
  payload: GeneratedCandidateUpdate;
};

type CandidateFormModel = {
  first_name: FormControl<string>;
  last_name: FormControl<string>;
  ihk_exam_number: FormControl<string>;
  specialization: FormControl<string>;
  training_company: FormControl<string>;
  attempt_number: FormControl<number>;
  requires_mep: FormControl<boolean>;
  exam_round_id: FormControl<number | null>;
  assignment_change_reason: FormControl<string>;
};

@Component({
  selector: 'app-candidates',
  imports: [
    AppIconDirective,
    FormsModule,
    ReactiveFormsModule,
    TuiButton,
    TuiBadge,
    TuiCheckbox,
    TuiForm,
    TuiHeader,
    TuiInput,
    TuiSelect,
    TuiTable,
    TuiTextfield,
  ],
  templateUrl: './candidates.component.html',
  styleUrl: './candidates.component.css',
})
export class CandidatesComponent {
  private readonly changeDetector = inject(ChangeDetectorRef);
  protected readonly icons = appIcons;
  @ViewChild('candidateCreateButton')
  private candidateCreateButton?: ElementRef<HTMLButtonElement>;
  @ViewChild('candidateCreateFormElement', { read: ElementRef })
  private candidateCreateFormElement?: ElementRef<HTMLFormElement>;

  @Input() masterData: MasterData | null = null;
  @Input() activeRound: ExamRound | null = null;
  @Input() actionBusy = false;

  @Output() createCandidate = new EventEmitter<CandidatePayload>();
  @Output() updateCandidate = new EventEmitter<CandidateUpdate>();
  @Output() deleteCandidate = new EventEmitter<Candidate>();

  protected readonly editingCandidateId = signal<number | null>(null);
  protected readonly editForm = signal<FormGroup<CandidateFormModel> | null>(null);
  protected readonly creatingCandidate = signal(false);
  protected readonly createValidationAttempted = signal(false);

  protected readonly query = signal('');
  protected readonly specialization = signal<string | null>(null);
  protected readonly candidateCreateForm = this.createForm();

  protected readonly specializationSelectOptions: readonly SelectOption<string>[] = [
    { value: 'application_development', label: 'Anwendungsentwicklung' },
    { value: 'system_integration', label: 'Systemintegration' },
    { value: 'data_and_process_analysis', label: 'Daten- und Prozessanalyse' },
    { value: 'digital_networking', label: 'Digitale Vernetzung' },
  ];
  protected readonly specializationOptions = selectValues(this.specializationSelectOptions);
  protected readonly specializationStringify = selectStringify(
    () => this.specializationSelectOptions,
  );
  protected readonly specializationFilterStringify = selectStringify(() =>
    this.specializationFilterSelectOptions(),
  );
  protected readonly eligibleRoundStringify = selectStringify(() =>
    this.eligibleRoundSelectOptions(),
  );

  protected candidateCount(): number {
    return this.masterData?.candidates.length ?? 0;
  }

  protected mepCount(): number {
    return (
      this.masterData?.candidates.filter((item) => item.roundCandidate?.requires_mep).length ?? 0
    );
  }

  protected attemptLabel(attempt?: number): string {
    return `${attempt ?? 1}. Versuch`;
  }

  protected specializations(): string[] {
    return [
      ...new Set(
        (this.masterData?.candidates ?? [])
          .map((item) => item.candidate.specialization)
          .filter(Boolean),
      ),
    ].sort((a, b) => this.specializationLabel(a).localeCompare(this.specializationLabel(b)));
  }

  protected specializationFilterOptions(): readonly string[] {
    return selectValues(this.specializationFilterSelectOptions());
  }

  protected filteredCandidates(): CandidateView[] {
    const query = this.query().trim().toLocaleLowerCase('de-DE');
    const specialization = this.specialization();
    return (this.masterData?.candidates ?? []).filter((item) => {
      const candidate = item.candidate;
      const matchesSpecialization = !specialization || candidate.specialization === specialization;
      const haystack = [
        candidate.first_name,
        candidate.last_name,
        candidate.ihk_exam_number,
        candidate.specialization,
        this.specializationLabel(candidate.specialization),
        candidate.training_company,
      ]
        .join(' ')
        .toLocaleLowerCase('de-DE');
      return matchesSpecialization && (!query || haystack.includes(query));
    });
  }

  protected specializationLabel(value: string): string {
    return selectLabel(this.specializationSelectOptions, value, value);
  }

  protected candidateLabel(candidate: Candidate): string {
    return `${candidate.first_name} ${candidate.last_name}`;
  }

  protected submitCandidate(): void {
    this.createValidationAttempted.set(true);
    this.candidateCreateForm.markAllAsTouched();
    if (this.candidateCreateForm.invalid) {
      this.changeDetector.detectChanges();
      this.candidateCreateFormElement?.nativeElement
        .querySelector<HTMLElement>('.app-form-error-summary')
        ?.focus();
      return;
    }

    this.createCandidate.emit(this.toPayload(this.candidateCreateForm));
  }

  resetDraft(): void {
    this.candidateCreateForm.reset(this.initialFormValue());
    this.candidateCreateForm.markAsPristine();
    this.candidateCreateForm.markAsUntouched();
    this.createValidationAttempted.set(false);
    this.creatingCandidate.set(false);
    this.focusCreateButton();
  }

  protected candidateCreateErrors(): readonly { field: string; message: string }[] {
    return [
      {
        field: 'candidateFirstName',
        control: this.candidateCreateForm.controls.first_name,
        message: 'Vorname eingeben.',
      },
      {
        field: 'candidateLastName',
        control: this.candidateCreateForm.controls.last_name,
        message: 'Nachname eingeben.',
      },
      {
        field: 'candidateExamNumber',
        control: this.candidateCreateForm.controls.ihk_exam_number,
        message: 'Prüfungsnummer eingeben.',
      },
    ].filter(({ control }) => control.invalid);
  }

  protected candidateCreateFieldInvalid(field: string): boolean {
    return (
      (this.createValidationAttempted() || Boolean(this.candidateCreateForm.get(field)?.touched)) &&
      this.candidateCreateErrors().some((error) => error.field === field)
    );
  }

  protected focusCandidateCreateField(field: string, event: Event): void {
    event.preventDefault();
    this.candidateCreateFormElement?.nativeElement.querySelector<HTMLElement>(`#${field}`)?.focus();
  }

  protected toggleCandidateCreation(): void {
    if (this.creatingCandidate()) {
      this.resetDraft();
      return;
    }

    this.creatingCandidate.set(true);
  }

  protected cancelCandidateCreation(): void {
    this.resetDraft();
  }

  protected startEditing(item: CandidateView): void {
    const activeAssignment = this.activeAssignment(item.candidate.id);
    this.editingCandidateId.set(item.candidate.id);
    this.editForm.set(
      this.createForm({
        first_name: item.candidate.first_name,
        last_name: item.candidate.last_name,
        ihk_exam_number: item.candidate.ihk_exam_number,
        specialization: item.candidate.specialization,
        training_company: item.candidate.training_company,
        attempt_number: item.roundCandidate?.attempt_number ?? 1,
        requires_mep: Boolean(item.roundCandidate?.requires_mep),
        exam_round_id: activeAssignment?.exam_round_id ?? this.activeRound?.id ?? null,
        assignment_change_reason: '',
      }),
    );
  }

  protected submitCandidateUpdate(): void {
    const id = this.editingCandidateId();
    const form = this.editForm();
    if (!id || !form) {
      return;
    }
    form.controls.assignment_change_reason.updateValueAndValidity();
    form.markAllAsTouched();
    if (form.invalid) {
      return;
    }
    this.updateCandidate.emit({ id, payload: this.toPayload(form) });
  }

  protected cancelEditing(): void {
    this.editingCandidateId.set(null);
    this.editForm.set(null);
  }

  finishEditing(id: number): void {
    if (this.editingCandidateId() === id) {
      this.cancelEditing();
    }
  }

  protected eligibleRounds(): ExamRound[] {
    const halfYearId = this.activeRound?.exam_half_year_id;
    if (!halfYearId) {
      return [];
    }
    return (
      this.masterData?.examRounds.filter((round) => round.exam_half_year_id === halfYearId) ?? []
    );
  }

  protected eligibleRoundIds(): readonly number[] {
    return selectValues(this.eligibleRoundSelectOptions());
  }

  protected assignmentHistory(candidateId: number): CandidateCommitteeAssignment[] {
    return (this.masterData?.candidateAssignments ?? [])
      .filter((assignment) => assignment.candidate_id === candidateId)
      .sort((left, right) => right.assigned_at.localeCompare(left.assigned_at));
  }

  protected activeAssignment(candidateId: number): CandidateCommitteeAssignment | undefined {
    return this.assignmentHistory(candidateId).find((assignment) => assignment.ended_at === null);
  }

  protected assignmentLabel(assignment: CandidateCommitteeAssignment): string {
    const round = this.masterData?.examRounds.find((item) => item.id === assignment.exam_round_id);
    return round ? this.roundLabel(round) : `Prüfungsrunde #${assignment.exam_round_id}`;
  }

  protected assignmentStateLabel(assignment: CandidateCommitteeAssignment): string {
    return assignment.ended_at ? 'beendet' : 'aktuell';
  }

  protected needsChangeReason(candidateId: number, targetRoundId?: number): boolean {
    const currentRoundId = this.activeAssignment(candidateId)?.exam_round_id;
    return (
      currentRoundId !== undefined &&
      targetRoundId !== undefined &&
      currentRoundId !== targetRoundId
    );
  }

  private roundLabel(round: ExamRound): string {
    const committee = this.masterData?.committees.find((item) => item.id === round.committee_id);
    return committee ? `${committee.name} · ${round.name}` : round.name;
  }

  private specializationFilterSelectOptions(): readonly SelectOption<string>[] {
    return this.specializations().map((value) => ({
      value,
      label: this.specializationLabel(value),
    }));
  }

  private eligibleRoundSelectOptions(): readonly SelectOption<number>[] {
    return this.eligibleRounds().map((round) => ({
      value: round.id,
      label: this.roundLabel(round),
    }));
  }

  private focusCreateButton(): void {
    queueMicrotask(() => this.candidateCreateButton?.nativeElement.focus());
  }

  private createForm(
    value: Partial<Record<keyof CandidateFormModel, unknown>> = {},
  ): FormGroup<CandidateFormModel> {
    const initial = this.initialFormValue();
    return new FormGroup({
      first_name: new FormControl(String(value.first_name ?? initial.first_name), {
        nonNullable: true,
        validators: [this.requiredText],
      }),
      last_name: new FormControl(String(value.last_name ?? initial.last_name), {
        nonNullable: true,
        validators: [this.requiredText],
      }),
      ihk_exam_number: new FormControl(String(value.ihk_exam_number ?? initial.ihk_exam_number), {
        nonNullable: true,
        validators: [this.requiredText],
      }),
      specialization: new FormControl(String(value.specialization ?? initial.specialization), {
        nonNullable: true,
        validators: [this.requiredText],
      }),
      training_company: new FormControl(
        String(value.training_company ?? initial.training_company),
        { nonNullable: true },
      ),
      attempt_number: new FormControl(Number(value.attempt_number ?? initial.attempt_number) || 1, {
        nonNullable: true,
        validators: [Validators.min(1)],
      }),
      requires_mep: new FormControl(Boolean(value.requires_mep ?? initial.requires_mep), {
        nonNullable: true,
      }),
      exam_round_id: new FormControl(
        (value.exam_round_id as number | null | undefined) ?? initial.exam_round_id,
      ),
      assignment_change_reason: new FormControl(String(value.assignment_change_reason ?? ''), {
        nonNullable: true,
        validators: [this.changeReasonValidator.bind(this)],
      }),
    });
  }

  private requiredText(control: AbstractControl) {
    return String(control.value).trim() ? null : { required: true };
  }

  private changeReasonValidator(control: AbstractControl): ValidationErrors | null {
    const roundId = control.parent?.get('exam_round_id')?.value as number | null | undefined;
    const candidateId = this.editingCandidateId();
    return candidateId &&
      this.needsChangeReason(candidateId, roundId ?? undefined) &&
      !String(control.value).trim()
      ? { required: true }
      : null;
  }

  private initialFormValue() {
    return {
      first_name: '',
      last_name: '',
      ihk_exam_number: '',
      specialization: 'application_development',
      training_company: '',
      attempt_number: 1,
      requires_mep: false,
      exam_round_id: null,
      assignment_change_reason: '',
    };
  }

  private toPayload(form: FormGroup<CandidateFormModel>): CandidatePayload {
    const value = form.getRawValue();
    return {
      first_name: value.first_name.trim(),
      last_name: value.last_name.trim(),
      ihk_exam_number: value.ihk_exam_number.trim(),
      specialization: value.specialization,
      training_company: value.training_company.trim(),
      attempt_number: Number(value.attempt_number) || 1,
      requires_mep: value.requires_mep ? 1 : 0,
      exam_round_id: value.exam_round_id ?? undefined,
      assignment_change_reason: value.assignment_change_reason.trim() || undefined,
    };
  }
}
