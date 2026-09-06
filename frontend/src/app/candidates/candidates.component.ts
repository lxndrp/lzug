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
import { FormsModule } from '@angular/forms';
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
import { appIcons } from '../app-icons';
import { AppIconDirective } from '../app-icon.directive';
import { type SelectOption, selectLabel, selectStringify, selectValues } from '../select-options';

export type CandidatePayload = Omit<Candidate, 'id'> & {
  attempt_number: number;
  requires_mep: number;
  exam_round_id?: number;
  assignment_change_reason?: string;
};
export type CandidateUpdate = {
  id: number;
  payload: CandidatePayload;
};

@Component({
  selector: 'app-candidates',
  imports: [
    AppIconDirective,
    FormsModule,
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
  @ViewChild('candidateCreateForm', { read: ElementRef })
  private candidateCreateForm?: ElementRef<HTMLFormElement>;

  @Input() masterData: MasterData | null = null;
  @Input() activeRound: ExamRound | null = null;
  @Input() actionBusy = false;

  @Output() createCandidate = new EventEmitter<CandidatePayload>();
  @Output() updateCandidate = new EventEmitter<CandidateUpdate>();
  @Output() deleteCandidate = new EventEmitter<Candidate>();

  protected readonly editingCandidateId = signal<number | null>(null);
  protected readonly editDraft = signal<CandidatePayload | null>(null);
  protected readonly creatingCandidate = signal(false);
  protected readonly createValidationAttempted = signal(false);

  protected readonly query = signal('');
  protected readonly specialization = signal<string | null>(null);
  protected readonly draft: CandidatePayload = {
    first_name: '',
    last_name: '',
    ihk_exam_number: '',
    specialization: 'application_development',
    training_company: '',
    attempt_number: 1,
    requires_mep: 0,
  };

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
    if (this.candidateCreateErrors().length) {
      this.changeDetector.detectChanges();
      this.candidateCreateForm?.nativeElement
        .querySelector<HTMLElement>('.app-form-error-summary')
        ?.focus();
      return;
    }

    this.createCandidate.emit({
      ...this.draft,
      first_name: this.draft.first_name.trim(),
      last_name: this.draft.last_name.trim(),
      ihk_exam_number: this.draft.ihk_exam_number.trim(),
      training_company: this.draft.training_company.trim(),
      attempt_number: Number(this.draft.attempt_number) || 1,
      requires_mep: this.draft.requires_mep ? 1 : 0,
    });
  }

  resetDraft(): void {
    this.candidateCreateForm?.nativeElement.reset();
    this.draft.first_name = '';
    this.draft.last_name = '';
    this.draft.ihk_exam_number = '';
    this.draft.specialization = 'application_development';
    this.draft.training_company = '';
    this.draft.attempt_number = 1;
    this.draft.requires_mep = 0;
    this.createValidationAttempted.set(false);
    this.creatingCandidate.set(false);
    this.focusCreateButton();
  }

  protected candidateCreateErrors(): readonly { field: string; message: string }[] {
    return [
      { field: 'candidateFirstName', message: 'Vorname eingeben.' },
      { field: 'candidateLastName', message: 'Nachname eingeben.' },
      { field: 'candidateExamNumber', message: 'Prüfungsnummer eingeben.' },
    ].filter(({ field }) => {
      if (field === 'candidateFirstName') return !this.draft.first_name.trim();
      if (field === 'candidateLastName') return !this.draft.last_name.trim();
      return !this.draft.ihk_exam_number.trim();
    });
  }

  protected candidateCreateFieldInvalid(field: string): boolean {
    return (
      this.createValidationAttempted() &&
      this.candidateCreateErrors().some((error) => error.field === field)
    );
  }

  protected focusCandidateCreateField(field: string, event: Event): void {
    event.preventDefault();
    this.candidateCreateForm?.nativeElement.querySelector<HTMLElement>(`#${field}`)?.focus();
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
    this.editDraft.set({
      first_name: item.candidate.first_name,
      last_name: item.candidate.last_name,
      ihk_exam_number: item.candidate.ihk_exam_number,
      specialization: item.candidate.specialization,
      training_company: item.candidate.training_company,
      attempt_number: item.roundCandidate?.attempt_number ?? 1,
      requires_mep: item.roundCandidate?.requires_mep ?? 0,
      exam_round_id: activeAssignment?.exam_round_id ?? this.activeRound?.id,
      assignment_change_reason: '',
    });
  }

  protected submitCandidateUpdate(): void {
    const id = this.editingCandidateId();
    const draft = this.editDraft();
    if (!id || !draft) {
      return;
    }

    const { exam_round_id, assignment_change_reason, ...candidateDraft } = draft;
    const payload: CandidatePayload = {
      ...candidateDraft,
      first_name: draft.first_name.trim(),
      last_name: draft.last_name.trim(),
      ihk_exam_number: draft.ihk_exam_number.trim(),
      training_company: draft.training_company.trim(),
      attempt_number: Number(draft.attempt_number) || 1,
      requires_mep: draft.requires_mep ? 1 : 0,
    };
    if (exam_round_id !== undefined) {
      payload.exam_round_id = exam_round_id;
    }
    const changeReason = assignment_change_reason?.trim();
    if (changeReason) {
      payload.assignment_change_reason = changeReason;
    }
    if (!payload.first_name || !payload.last_name || !payload.ihk_exam_number) {
      return;
    }

    this.updateCandidate.emit({ id, payload });
  }

  protected cancelEditing(): void {
    this.editingCandidateId.set(null);
    this.editDraft.set(null);
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
}
