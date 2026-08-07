import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TuiButton, TuiInput, TuiNotification, TuiTextfield } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';
import { TuiForm, TuiHeader } from '@taiga-ui/layout';

import {
  CandidateCommitteeAssignment,
  CandidateView,
  Committee,
  CommitteeMember,
  ExamHalfYear,
  ExamRound,
} from '../api/api.models';
import { PlanningApiService } from '../api/planning-api.service';
import { appIcons } from '../app-icons';
import { AppIconDirective } from '../app-icon.directive';

export type HalfYearDraft = Pick<ExamHalfYear, 'season' | 'year'>;

/** Manage exam half-years and the committee-specific rounds within one selected context. */
@Component({
  selector: 'app-exam-half-years',
  imports: [
    AppIconDirective,
    FormsModule,
    TuiBadge,
    TuiButton,
    TuiForm,
    TuiHeader,
    TuiInput,
    TuiNotification,
    TuiTextfield,
  ],
  templateUrl: './exam-half-years.component.html',
})
export class ExamHalfYearsComponent implements OnInit {
  private readonly api = inject(PlanningApiService);

  protected readonly icons = appIcons;
  protected readonly halfYears = signal<ExamHalfYear[]>([]);
  protected readonly rounds = signal<ExamRound[]>([]);
  protected readonly selectedHalfYearId = signal<number | null>(null);
  protected readonly creatingHalfYear = signal(false);
  protected readonly editingHalfYearId = signal<number | null>(null);
  protected readonly editDraft = signal<HalfYearDraft | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly success = signal<string | null>(null);

  protected readonly halfYearDraft: HalfYearDraft = {
    season: 'summer',
    year: new Date().getFullYear(),
  };

  @Input() committees: Committee[] = [];
  @Input() members: CommitteeMember[] = [];
  @Input() candidates: CandidateView[] = [];
  @Input() candidateAssignments: CandidateCommitteeAssignment[] = [];
  @Input() activeRoundId: number | null = null;
  @Output() roundSelected = new EventEmitter<number>();

  ngOnInit(): void {
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.listExamHalfYears().subscribe({
      next: (halfYears) => {
        this.halfYears.set(halfYears);
        this.api.listExamRounds().subscribe({
          next: (rounds) => {
            this.rounds.set(rounds);
            this.ensureSelectedHalfYear(halfYears, rounds);
            this.loading.set(false);
          },
          error: () => this.loadError(),
        });
      },
      error: () => this.loadError(),
    });
  }

  protected toggleHalfYearCreation(): void {
    this.creatingHalfYear.set(!this.creatingHalfYear());
    this.error.set(null);
  }

  protected cancelHalfYearCreation(): void {
    this.creatingHalfYear.set(false);
    this.halfYearDraft.season = 'summer';
    this.halfYearDraft.year = new Date().getFullYear();
  }

  protected createHalfYear(event: SubmitEvent): void {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    const data = new FormData(form);
    const year = Number(data.get('year'));
    const season = String(data.get('season')) as ExamHalfYear['season'];
    if (!Number.isInteger(year) || !season) {
      return;
    }
    this.loading.set(true);
    this.api.createExamHalfYear({ season, year, status: 'draft' }).subscribe({
      next: (halfYear) => {
        this.creatingHalfYear.set(false);
        this.selectedHalfYearId.set(halfYear.id);
        this.success.set('Prüfungshalbjahr angelegt. Öffnen Sie es, um Ausschüsse zu verwalten.');
        this.load();
      },
      error: () => this.saveError('Das Prüfungshalbjahr konnte nicht angelegt werden.'),
    });
  }

  protected startEditing(halfYear: ExamHalfYear): void {
    if (!this.canEdit(halfYear)) {
      return;
    }
    this.editingHalfYearId.set(halfYear.id);
    this.editDraft.set({ season: halfYear.season as ExamHalfYear['season'], year: halfYear.year });
  }

  protected submitHalfYearUpdate(): void {
    const id = this.editingHalfYearId();
    const draft = this.editDraft();
    if (!id || !draft || !Number.isInteger(Number(draft.year))) {
      return;
    }
    this.loading.set(true);
    this.api
      .updateExamHalfYear(id, {
        season: draft.season,
        year: Number(draft.year),
      })
      .subscribe({
        next: () => {
          this.editingHalfYearId.set(null);
          this.editDraft.set(null);
          this.success.set('Prüfungshalbjahr aktualisiert.');
          this.load();
        },
        error: () => this.saveError('Das Prüfungshalbjahr konnte nicht aktualisiert werden.'),
      });
  }

  protected cancelEditing(): void {
    this.editingHalfYearId.set(null);
    this.editDraft.set(null);
  }

  protected selectHalfYear(halfYear: ExamHalfYear): void {
    this.selectedHalfYearId.set(halfYear.id);
    this.editingHalfYearId.set(null);
    this.editDraft.set(null);
    this.error.set(null);
  }

  protected createRound(event: SubmitEvent): void {
    event.preventDefault();
    const data = new FormData(event.currentTarget as HTMLFormElement);
    const halfYear = this.selectedHalfYear();
    const committeeId = Number(data.get('committee_id'));
    const creatorId = Number(data.get('created_by_member_id'));
    const creator = this.members.find(
      (member) => member.id === creatorId && member.committee_id === committeeId,
    );
    const committee = this.committees.find((item) => item.id === committeeId);
    if (!halfYear || !committee || !creator || !this.canManageRounds(halfYear)) {
      this.error.set('Für das ausgewählte Halbjahr und den Ausschuss fehlen Angaben.');
      return;
    }
    this.loading.set(true);
    this.api
      .createExamRound({
        exam_half_year_id: halfYear.id,
        committee_id: committeeId,
        created_by_member_id: creator.id,
        name: `${this.halfYearLabel(halfYear)} · ${committee.name}`,
      })
      .subscribe({
        next: (round) => {
          this.success.set('Ausschuss dem Prüfungshalbjahr zugeordnet.');
          this.roundSelected.emit(round.id);
          this.load();
        },
        error: () =>
          this.saveError(
            'Der Ausschuss konnte nicht zugeordnet werden. Jeder Ausschuss ist je Prüfungshalbjahr nur einmal zulässig.',
          ),
      });
  }

  protected halfYearLabel(halfYear: ExamHalfYear): string {
    return `${halfYear.season === 'summer' ? 'Sommer' : 'Winter'} ${halfYear.year}`;
  }

  protected memberRoleLabel(role: string): string {
    return (
      {
        chair: 'Vorsitz',
        deputy_chair: 'Stellvertretender Vorsitz',
        member: 'Mitglied',
      }[role] ?? role
    );
  }

  protected statusLabel(status: string): string {
    const labels: Record<string, string> = {
      draft: 'Entwurf',
      active: 'In Bearbeitung',
      completed: 'Abgeschlossen',
      archived: 'Archiviert',
    };
    return labels[status] ?? status;
  }

  protected statusAppearance(status: string): string {
    const appearances: Record<string, string> = {
      draft: 'neutral',
      active: 'warning',
      completed: 'positive',
      archived: 'info',
    };
    return appearances[status] ?? 'neutral';
  }

  protected selectedHalfYear(): ExamHalfYear | null {
    const selectedId = this.selectedHalfYearId();
    return this.halfYears().find((halfYear) => halfYear.id === selectedId) ?? null;
  }

  protected roundsFor(halfYear: ExamHalfYear): Array<{ round: ExamRound; committee?: Committee }> {
    return this.rounds()
      .filter((round) => round.exam_half_year_id === halfYear.id)
      .map((round) => ({
        round,
        committee: this.committees.find((committee) => committee.id === round.committee_id),
      }));
  }

  protected candidateCountFor(halfYear: ExamHalfYear): number {
    return new Set(
      this.candidateAssignments
        .filter(
          (assignment) => assignment.exam_half_year_id === halfYear.id && !assignment.ended_at,
        )
        .map((assignment) => assignment.candidate_id),
    ).size;
  }

  protected progressLabel(halfYear: ExamHalfYear): string {
    const rounds = this.roundsFor(halfYear);
    if (!rounds.length) {
      return 'Noch keine Prüfungsrunden';
    }
    const confirmed = rounds.filter((entry) => entry.round.status === 'plan_confirmed').length;
    return `${confirmed} von ${rounds.length} Prüfungsrunden bestätigt`;
  }

  protected committeeCountFor(halfYear: ExamHalfYear): number {
    return new Set(this.roundsFor(halfYear).map((entry) => entry.round.committee_id)).size;
  }

  protected canEdit(halfYear: ExamHalfYear): boolean {
    return !['completed', 'archived'].includes(halfYear.status);
  }

  protected canManageRounds(halfYear: ExamHalfYear): boolean {
    return !['completed', 'archived'].includes(halfYear.status);
  }

  protected canComplete(): boolean {
    return false;
  }

  protected canArchive(halfYear: ExamHalfYear): boolean {
    return halfYear.status === 'completed';
  }

  protected statusActionHint(halfYear: ExamHalfYear): string {
    if (halfYear.status === 'completed') {
      return 'Das Halbjahr kann archiviert werden.';
    }
    return 'Abschluss und Archivierung folgen der fachlichen Abschlusslogik aus #89.';
  }

  protected selectRound(round: ExamRound): void {
    this.selectedHalfYearId.set(round.exam_half_year_id);
    this.roundSelected.emit(round.id);
  }

  private ensureSelectedHalfYear(halfYears: ExamHalfYear[], rounds: ExamRound[]): void {
    const currentSelection = this.selectedHalfYearId();
    if (currentSelection && halfYears.some((halfYear) => halfYear.id === currentSelection)) {
      return;
    }
    const activeHalfYearId = rounds.find(
      (round) => round.id === this.activeRoundId,
    )?.exam_half_year_id;
    this.selectedHalfYearId.set(activeHalfYearId ?? halfYears[0]?.id ?? null);
  }

  private loadError(): void {
    this.loading.set(false);
    this.error.set('Prüfungshalbjahre konnten nicht geladen werden.');
  }

  private saveError(message: string): void {
    this.loading.set(false);
    this.error.set(message);
  }
}
