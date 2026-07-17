import { Component, EventEmitter, Input, Output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TuiButton, TuiInput, TuiTextfield } from '@taiga-ui/core';
import { TuiTable } from '@taiga-ui/addon-table';

import { Candidate, CandidateView, MasterData } from '../api/api.models';
import { appIcons } from '../app-icons';
import { AppIconDirective } from '../app-icon.directive';

export type CandidatePayload = Omit<Candidate, 'id'> & {
  attempt_number: number;
  requires_mep: number;
};
export type CandidateUpdate = {
  id: number;
  payload: CandidatePayload;
};

@Component({
  selector: 'app-candidates',
  imports: [AppIconDirective, FormsModule, TuiButton, TuiInput, TuiTable, TuiTextfield],
  templateUrl: './candidates.component.html',
})
export class CandidatesComponent {
  protected readonly icons = appIcons;
  @Input() masterData: MasterData | null = null;
  @Input() actionBusy = false;

  @Output() createCandidate = new EventEmitter<CandidatePayload>();
  @Output() updateCandidate = new EventEmitter<CandidateUpdate>();
  @Output() deleteCandidate = new EventEmitter<Candidate>();

  protected readonly editingCandidateId = signal<number | null>(null);
  protected readonly editDraft = signal<CandidatePayload | null>(null);

  protected readonly query = signal('');
  protected readonly specialization = signal('');
  protected readonly draft: CandidatePayload = {
    first_name: '',
    last_name: '',
    ihk_exam_number: '',
    specialization: 'application_development',
    training_company: '',
    attempt_number: 1,
    requires_mep: 0,
  };

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
    const labels: Record<string, string> = {
      application_development: 'Anwendungsentwicklung',
      system_integration: 'Systemintegration',
      data_and_process_analysis: 'Daten- und Prozessanalyse',
      digital_networking: 'Digitale Vernetzung',
    };
    return labels[value] ?? value;
  }

  protected submitCandidate(): void {
    if (
      !this.draft.first_name.trim() ||
      !this.draft.last_name.trim() ||
      !this.draft.ihk_exam_number.trim()
    ) {
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
    this.resetDraft();
  }

  resetDraft(): void {
    this.draft.first_name = '';
    this.draft.last_name = '';
    this.draft.ihk_exam_number = '';
    this.draft.specialization = 'application_development';
    this.draft.training_company = '';
    this.draft.attempt_number = 1;
    this.draft.requires_mep = 0;
  }

  protected startEditing(item: CandidateView): void {
    this.editingCandidateId.set(item.candidate.id);
    this.editDraft.set({
      first_name: item.candidate.first_name,
      last_name: item.candidate.last_name,
      ihk_exam_number: item.candidate.ihk_exam_number,
      specialization: item.candidate.specialization,
      training_company: item.candidate.training_company,
      attempt_number: item.roundCandidate?.attempt_number ?? 1,
      requires_mep: item.roundCandidate?.requires_mep ?? 0,
    });
  }

  protected submitCandidateUpdate(): void {
    const id = this.editingCandidateId();
    const draft = this.editDraft();
    if (!id || !draft) {
      return;
    }

    const payload: CandidatePayload = {
      ...draft,
      first_name: draft.first_name.trim(),
      last_name: draft.last_name.trim(),
      ihk_exam_number: draft.ihk_exam_number.trim(),
      training_company: draft.training_company.trim(),
      attempt_number: Number(draft.attempt_number) || 1,
      requires_mep: draft.requires_mep ? 1 : 0,
    };
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
}
