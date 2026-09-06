import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TuiButton, TuiInput, TuiNotification, TuiTextfield } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';
import { TuiForm, TuiHeader } from '@taiga-ui/layout';

import {
  CandidateCommitteeAssignment,
  CandidateView,
  Committee,
  ExamHalfYear,
  ExamRound,
  ExamRoundLifecycle,
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
  styleUrl: './exam-half-years.component.css',
})
export class ExamHalfYearsComponent implements OnInit {
  private readonly api = inject(PlanningApiService);

  protected readonly icons = appIcons;
  protected readonly halfYears = signal<ExamHalfYear[]>([]);
  protected readonly rounds = signal<ExamRound[]>([]);
  protected readonly lifecycles = signal<Record<number, ExamRoundLifecycle>>({});
  protected readonly selectedHalfYearId = signal<number | null>(null);
  protected readonly creatingHalfYear = signal(false);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly success = signal<string | null>(null);

  protected readonly halfYearDraft: HalfYearDraft = {
    season: 'summer',
    year: new Date().getFullYear(),
  };

  @Input() committees: Committee[] = [];
  @Input() candidates: CandidateView[] = [];
  @Input() candidateAssignments: CandidateCommitteeAssignment[] = [];
  @Input() activeRoundId: number | null = null;
  @Input() readOnly = false;
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
            this.loadLifecycles(rounds);
            this.loading.set(false);
          },
          error: () => this.loadError(),
        });
      },
      error: () => this.loadError(),
    });
  }

  protected toggleHalfYearCreation(): void {
    if (this.readOnly) return;
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
    if (this.readOnly) return;
    const form = event.currentTarget as HTMLFormElement;
    const data = new FormData(form);
    const year = Number(data.get('year'));
    const season = String(data.get('season')) as ExamHalfYear['season'];
    const committeeId = Number(data.get('committee_id'));
    const committee = this.committees.find((item) => item.id === committeeId);
    if (!Number.isInteger(year) || !season || !committee) {
      return;
    }
    this.loading.set(true);
    this.api
      .createExamRound({
        season,
        year,
        committee_id: committee.id,
        name: `${season === 'summer' ? 'Sommer' : 'Winter'} ${year} · ${committee.name}`,
      })
      .subscribe({
        next: (round) => {
          this.creatingHalfYear.set(false);
          this.success.set('Prüfungsrunde und gemeinsamer Halbjahreskontext wurden angelegt.');
          this.roundSelected.emit(round.id);
          this.load();
        },
        error: () => this.saveError('Die Prüfungsrunde konnte nicht angelegt werden.'),
      });
  }

  protected selectHalfYear(halfYear: ExamHalfYear): void {
    this.selectedHalfYearId.set(halfYear.id);
    this.error.set(null);
  }

  protected createRound(event: SubmitEvent): void {
    event.preventDefault();
    if (this.readOnly) return;
    const data = new FormData(event.currentTarget as HTMLFormElement);
    const halfYear = this.selectedHalfYear();
    const committeeId = Number(data.get('committee_id'));
    const committee = this.committees.find((item) => item.id === committeeId);
    if (!halfYear || !committee || !this.canManageRounds(halfYear)) {
      this.error.set('Für das ausgewählte Halbjahr und den Ausschuss fehlen Angaben.');
      return;
    }
    this.loading.set(true);
    this.api
      .createExamRound({
        exam_half_year_id: halfYear.id,
        committee_id: committeeId,
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

  protected statusLabel(status: string): string {
    const labels: Record<string, string> = {
      draft: 'Entwurf',
      active: 'In Bearbeitung',
      completed: 'Abgeschlossen',
      archived: 'Archiviert',
      open: 'Offen',
      closed: 'Abgeschlossen',
      cancelled: 'Abgesagt',
      reopening: 'Wieder geöffnet',
      historical: 'Historisch',
    };
    return labels[status] ?? status;
  }

  protected statusAppearance(status: string): string {
    const appearances: Record<string, string> = {
      draft: 'neutral',
      active: 'warning',
      completed: 'positive',
      archived: 'info',
      open: 'warning',
      closed: 'positive',
      cancelled: 'negative',
      reopening: 'warning',
      historical: 'info',
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

  protected canManageRounds(halfYear: ExamHalfYear): boolean {
    return !this.readOnly && !['completed', 'archived'].includes(halfYear.status);
  }

  protected selectRound(round: ExamRound): void {
    this.selectedHalfYearId.set(round.exam_half_year_id);
    this.roundSelected.emit(round.id);
  }

  protected lifecycleFor(roundId: number): ExamRoundLifecycle | null {
    return this.lifecycles()[roundId] ?? null;
  }

  protected candidateName(candidateId: number): string {
    const candidate = this.candidates.find((item) => item.candidate.id === candidateId)?.candidate;
    return candidate ? `${candidate.first_name} ${candidate.last_name}` : `Prüfling ${candidateId}`;
  }

  protected setCandidateTerminalStatus(
    round: ExamRound,
    roundCandidateId: number,
    terminalStatus: string,
    reason: string,
    detail: string,
  ): void {
    const lifecycle = this.lifecycleFor(round.id);
    if (this.readOnly || !lifecycle || !terminalStatus) return;
    const payload: {
      revision: number;
      terminal_status: string;
      reason?: string;
      effective_new_round_id?: number;
      postponed_until?: string;
      ihk_decision_reference?: string;
    } = { revision: lifecycle.revision, terminal_status: terminalStatus };
    if (reason.trim()) payload.reason = reason.trim();
    if (terminalStatus === 'transferred') payload.effective_new_round_id = Number(detail);
    if (terminalStatus === 'postponed') payload.postponed_until = detail.trim();
    if (terminalStatus === 'ihk_terminated') payload.ihk_decision_reference = detail.trim();
    this.loading.set(true);
    this.api.setRoundCandidateTerminalStatus(round.id, roundCandidateId, payload).subscribe({
      next: (updated) =>
        this.lifecycleSaved(round.id, updated, 'Abschließender Prüflingsstatus gespeichert.'),
      error: () => this.saveError('Der Prüflingsstatus ist unvollständig oder widersprüchlich.'),
    });
  }

  protected documentIhkStatus(
    round: ExamRound,
    resultId: number,
    documentStatus: string,
    reference: string,
  ): void {
    if (
      this.readOnly ||
      !Number.isInteger(resultId) ||
      !documentStatus.trim() ||
      !reference.trim()
    ) {
      return;
    }
    this.loading.set(true);
    this.api
      .documentExamRoundIhkStatus(round.id, resultId, documentStatus.trim(), reference.trim())
      .subscribe({
        next: (updated) =>
          this.lifecycleSaved(round.id, updated, 'Förmlicher IHK-Status dokumentiert.'),
        error: () => this.saveError('Der IHK-Status konnte nicht dokumentiert werden.'),
      });
  }

  protected closeRound(round: ExamRound, confirmed: boolean): void {
    const lifecycle = this.lifecycleFor(round.id);
    if (this.readOnly || !lifecycle || !confirmed) return;
    this.loading.set(true);
    this.api.closeExamRound(round.id, lifecycle.revision).subscribe({
      next: (updated) => this.lifecycleSaved(round.id, updated, 'Prüfungsrunde abgeschlossen.'),
      error: () => this.saveError('Die Prüfungsrunde konnte nicht abgeschlossen werden.'),
    });
  }

  protected cancelRound(round: ExamRound, reason: string, confirmed: boolean): void {
    const lifecycle = this.lifecycleFor(round.id);
    if (this.readOnly || !lifecycle || !confirmed || !reason.trim()) return;
    this.loading.set(true);
    this.api.cancelExamRound(round.id, lifecycle.revision, reason.trim()).subscribe({
      next: (updated) => this.lifecycleSaved(round.id, updated, 'Prüfungsrunde abgesagt.'),
      error: () => this.saveError('Die Prüfungsrunde konnte nicht abgesagt werden.'),
    });
  }

  protected reopenRound(
    round: ExamRound,
    occasion: string,
    source: string,
    reason: string,
    scopeKind: string,
    scopeId: number,
    confirmed: boolean,
  ): void {
    const lifecycle = this.lifecycleFor(round.id);
    if (
      this.readOnly ||
      !lifecycle ||
      !confirmed ||
      !occasion.trim() ||
      !source.trim() ||
      !reason.trim() ||
      !scopeKind ||
      !Number.isInteger(scopeId)
    ) {
      return;
    }
    this.loading.set(true);
    this.api
      .reopenExamRound(round.id, {
        revision: lifecycle.revision,
        occasion: occasion.trim(),
        source: source.trim(),
        reason: reason.trim(),
        scope: [{ kind: scopeKind, entity_id: scopeId }],
      })
      .subscribe({
        next: (updated) =>
          this.lifecycleSaved(round.id, updated, 'Prüfungsrunde gezielt wieder geöffnet.'),
        error: () => this.saveError('Die Prüfungsrunde konnte nicht wieder geöffnet werden.'),
      });
  }

  protected deleteRound(round: ExamRound, confirmed: boolean): void {
    const lifecycle = this.lifecycleFor(round.id);
    if (this.readOnly || !lifecycle?.permissions.delete || !confirmed) return;
    this.loading.set(true);
    this.api.deleteEmptyExamRound(round.id).subscribe({
      next: () => {
        this.success.set('Leere Entwurfsrunde gelöscht.');
        this.load();
      },
      error: () => this.saveError('Nur eine vollständig leere Entwurfsrunde kann gelöscht werden.'),
    });
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

  private loadLifecycles(rounds: ExamRound[]): void {
    this.lifecycles.set({});
    for (const round of rounds) {
      this.api.getExamRoundLifecycle(round.id).subscribe({
        next: (lifecycle) =>
          this.lifecycles.update((current) => ({ ...current, [round.id]: lifecycle })),
      });
    }
  }

  private lifecycleSaved(roundId: number, lifecycle: ExamRoundLifecycle, message: string): void {
    this.lifecycles.update((current) => ({ ...current, [roundId]: lifecycle }));
    this.loading.set(false);
    this.success.set(message);
    this.error.set(null);
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
