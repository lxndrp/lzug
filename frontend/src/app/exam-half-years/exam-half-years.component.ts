import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TuiButton, TuiInput, TuiNotification, TuiTextfield } from '@taiga-ui/core';
import { TuiBadge, TuiSelect } from '@taiga-ui/kit';
import { TuiForm, TuiHeader } from '@taiga-ui/layout';

import { Committee, CommitteeMember, ExamHalfYear, ExamRound } from '../api/api.models';
import { PlanningApiService } from '../api/planning-api.service';

/** Manage global terms and the one committee-specific round belonging to each term. */
@Component({
  selector: 'app-exam-half-years',
  imports: [
    FormsModule,
    TuiBadge,
    TuiButton,
    TuiForm,
    TuiHeader,
    TuiInput,
    TuiNotification,
    TuiSelect,
    TuiTextfield,
  ],
  templateUrl: './exam-half-years.component.html',
})
export class ExamHalfYearsComponent implements OnInit {
  private readonly api = inject(PlanningApiService);
  protected readonly halfYears = signal<ExamHalfYear[]>([]);
  protected readonly rounds = signal<ExamRound[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly success = signal<string | null>(null);

  @Input() committees: Committee[] = [];
  @Input() members: CommitteeMember[] = [];
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
            this.loading.set(false);
          },
          error: () => this.loadError(),
        });
      },
      error: () => this.loadError(),
    });
  }

  protected createHalfYear(event: SubmitEvent): void {
    event.preventDefault();
    const data = new FormData(event.currentTarget as HTMLFormElement);
    const year = Number(data.get('year'));
    const season = String(data.get('season')) as ExamHalfYear['season'];
    if (!Number.isInteger(year) || !season) {
      return;
    }
    this.loading.set(true);
    this.api.createExamHalfYear({ season, year, status: 'draft' }).subscribe({
      next: () => {
        (event.currentTarget as HTMLFormElement).reset();
        this.success.set('Prüfungshalbjahr angelegt. Ordnen Sie jetzt Ausschüsse zu.');
        this.load();
      },
      error: () => this.saveError('Das Prüfungshalbjahr konnte nicht angelegt werden.'),
    });
  }

  protected createRound(event: SubmitEvent): void {
    event.preventDefault();
    const data = new FormData(event.currentTarget as HTMLFormElement);
    const halfYearId = Number(data.get('exam_half_year_id'));
    const committeeId = Number(data.get('committee_id'));
    const creator =
      this.members.find(
        (member) => member.committee_id === committeeId && member.committee_role === 'chair',
      ) ?? this.members.find((member) => member.committee_id === committeeId);
    const halfYear = this.halfYears().find((item) => item.id === halfYearId);
    const committee = this.committees.find((item) => item.id === committeeId);
    if (!halfYear || !committee || !creator) {
      this.error.set('Für den ausgewählten Ausschuss muss mindestens ein Prüfer hinterlegt sein.');
      return;
    }
    this.loading.set(true);
    this.api
      .createExamRound({
        exam_half_year_id: halfYearId,
        committee_id: committeeId,
        created_by_member_id: creator.id,
        name: `${this.halfYearLabel(halfYear)} · ${committee.name}`,
      })
      .subscribe({
        next: (round) => {
          this.success.set('Ausschussbezogene Prüfungsrunde angelegt.');
          this.roundSelected.emit(round.id);
          this.load();
        },
        error: () =>
          this.saveError(
            'Die Prüfungsrunde konnte nicht angelegt werden. Jeder Ausschuss ist je Prüfungshalbjahr nur einmal zulässig.',
          ),
      });
  }

  protected halfYearLabel(halfYear: ExamHalfYear): string {
    return `${halfYear.season === 'summer' ? 'Sommer' : 'Winter'} ${halfYear.year}`;
  }

  protected roundsFor(halfYear: ExamHalfYear): Array<{ round: ExamRound; committee?: Committee }> {
    return this.rounds()
      .filter((round) => round.exam_half_year_id === halfYear.id)
      .map((round) => ({
        round,
        committee: this.committees.find((committee) => committee.id === round.committee_id),
      }));
  }

  protected selectRound(round: ExamRound): void {
    this.roundSelected.emit(round.id);
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
