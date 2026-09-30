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
import {
  TuiButton,
  TuiCheckbox,
  TuiError,
  TuiInput,
  TuiTextfield,
  tuiValidationErrorsProvider,
} from '@taiga-ui/core';
import { TuiBadge, TuiSelect } from '@taiga-ui/kit';
import { TuiTable } from '@taiga-ui/addon-table';
import { TuiForm, TuiHeader } from '@taiga-ui/layout';

import type {
  Candidate,
  CandidateCommand,
  CandidateExamRound,
  CandidateUpdate as CandidateUpdateCommandWithId,
  CandidateView,
  CandidateWorkspace,
} from '../master-data/master-data.models';
import { appIcons } from '../app-icons';
import { AppIconDirective } from '../app-icon.directive';
import { type SelectOption, selectLabel, selectStringify, selectValues } from '../select-options';

export type CandidatePayload = CandidateCommand;
export type CandidateUpdate = CandidateUpdateCommandWithId;

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
    TuiError,
    TuiForm,
    TuiHeader,
    TuiInput,
    TuiSelect,
    TuiTable,
    TuiTextfield,
  ],
  providers: [
    tuiValidationErrorsProvider({
      candidateExamNumberRequired: 'Prüfungsnummer eingeben.',
      candidateFirstNameRequired: 'Vorname eingeben.',
      candidateLastNameRequired: 'Nachname eingeben.',
    }),
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

  @Input() masterData: CandidateWorkspace | null = null;
  @Input() activeRound: CandidateWorkspace['activeRound'] = null;
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
      this.masterData?.candidates.filter((item) => item.roundCandidate?.requiresMep).length ?? 0
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
        candidate.firstName,
        candidate.lastName,
        candidate.examNumber,
        candidate.specialization,
        this.specializationLabel(candidate.specialization),
        candidate.trainingCompany,
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
    return `${candidate.firstName} ${candidate.lastName}`;
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
        first_name: item.candidate.firstName,
        last_name: item.candidate.lastName,
        ihk_exam_number: item.candidate.examNumber,
        specialization: item.candidate.specialization,
        training_company: item.candidate.trainingCompany,
        attempt_number: item.roundCandidate?.attemptNumber ?? 1,
        requires_mep: item.roundCandidate?.requiresMep ?? false,
        exam_round_id: activeAssignment?.examRoundId ?? this.activeRound?.id ?? null,
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

  protected eligibleRounds(): CandidateExamRound[] {
    const halfYearId = this.activeRound?.halfYearId;
    if (!halfYearId) {
      return [];
    }
    return this.masterData?.examRounds.filter((round) => round.halfYearId === halfYearId) ?? [];
  }

  protected eligibleRoundIds(): readonly number[] {
    return selectValues(this.eligibleRoundSelectOptions());
  }

  protected assignmentHistory(candidateId: number) {
    return (this.masterData?.assignments ?? [])
      .filter((assignment) => assignment.candidateId === candidateId)
      .sort((left, right) => right.assignedAt.localeCompare(left.assignedAt));
  }

  protected activeAssignment(candidateId: number) {
    return this.assignmentHistory(candidateId).find((assignment) => assignment.endedAt === null);
  }

  protected assignmentLabel(assignment: CandidateWorkspace['assignments'][number]): string {
    const round = this.masterData?.examRounds.find((item) => item.id === assignment.examRoundId);
    return round ? this.roundLabel(round) : `Prüfungsrunde #${assignment.examRoundId}`;
  }

  protected assignmentStateLabel(assignment: CandidateWorkspace['assignments'][number]): string {
    return assignment.endedAt ? 'beendet' : 'aktuell';
  }

  protected needsChangeReason(candidateId: number, targetRoundId?: number): boolean {
    const currentRoundId = this.activeAssignment(candidateId)?.examRoundId;
    return (
      currentRoundId !== undefined &&
      targetRoundId !== undefined &&
      currentRoundId !== targetRoundId
    );
  }

  private roundLabel(round: CandidateExamRound): string {
    const committee = this.masterData?.committees.find((item) => item.id === round.committeeId);
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
        validators: [this.requiredText('candidateFirstNameRequired')],
      }),
      last_name: new FormControl(String(value.last_name ?? initial.last_name), {
        nonNullable: true,
        validators: [this.requiredText('candidateLastNameRequired')],
      }),
      ihk_exam_number: new FormControl(String(value.ihk_exam_number ?? initial.ihk_exam_number), {
        nonNullable: true,
        validators: [this.requiredText('candidateExamNumberRequired')],
      }),
      specialization: new FormControl(String(value.specialization ?? initial.specialization), {
        nonNullable: true,
        validators: [this.requiredTextValidator],
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

  private requiredText(error: string) {
    return (control: AbstractControl) => (String(control.value).trim() ? null : { [error]: true });
  }

  private requiredTextValidator(control: AbstractControl) {
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
      firstName: value.first_name.trim(),
      lastName: value.last_name.trim(),
      examNumber: value.ihk_exam_number.trim(),
      specialization: value.specialization,
      trainingCompany: value.training_company.trim(),
      attemptNumber: Number(value.attempt_number) || 1,
      requiresMep: value.requires_mep,
      examRoundId: value.exam_round_id ?? undefined,
      assignmentChangeReason: value.assignment_change_reason.trim() || undefined,
    };
  }
}
