import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { finalize } from 'rxjs';

import type { ExamRound, MasterData, PlanningBoard, RoundSummary } from '../api/api.models';
import { ApplicationError } from '../api/application-error';
import { PlanningApiService } from '../api/planning-api.service';
import { RoundContextService } from '../api/round-context.service';
import { AuthService } from '../auth/auth.service';
import { UiFeedbackService } from './ui-feedback.service';

/** Coherent application-wide read state shared by shell and feature coordinators. */
@Injectable({ providedIn: 'root' })
export class ApplicationWorkspaceService {
  private readonly api = inject(PlanningApiService);
  private readonly auth = inject(AuthService);
  private readonly feedback = inject(UiFeedbackService);
  private readonly roundContext = inject(RoundContextService);
  private readonly router = inject(Router);

  readonly round = signal<ExamRound | null>(null);
  readonly summary = signal<RoundSummary | null>(null);
  readonly board = signal<PlanningBoard | null>(null);
  readonly masterData = signal<MasterData | null>(null);
  readonly selectedCommitteeId = signal<number | null>(null);
  readonly message = signal('Bereit');
  readonly loading = signal(false);
  readonly actionBusy = signal(false);
  readonly applicationVersion = signal<string | null>(null);
  readonly masterDataError = signal(false);
  private refreshGeneration = 0;

  refresh(): void {
    if (this.auth.state() !== 'authenticated') return;
    const roundId = this.roundContext.roundId();
    const generation = ++this.refreshGeneration;
    if (this.round() && this.round()?.id !== roundId) {
      this.round.set(null);
      this.summary.set(null);
      this.board.set(null);
      this.masterData.set(null);
    }
    this.masterDataError.set(false);
    this.loading.set(true);
    this.api
      .refreshDashboard(roundId)
      .pipe(
        finalize(() => {
          if (generation === this.refreshGeneration) this.loading.set(false);
        }),
      )
      .subscribe({
        next: ({ root, round, summary, board, masterData }) => {
          if (generation !== this.refreshGeneration || this.roundContext.roundId() !== roundId) {
            return;
          }
          this.masterDataError.set(false);
          this.applicationVersion.set(root.version);
          this.round.set(round);
          this.summary.set(summary);
          this.board.set(board);
          this.masterData.set(masterData);
          if (!this.selectedCommitteeId()) {
            this.selectedCommitteeId.set(masterData.committees[0]?.id ?? null);
          }
          if (
            this.router.url.startsWith('/scheduling-overview/') &&
            round.status === 'plan_confirmed'
          ) {
            void this.router.navigateByUrl(`/confirmed-plans/${round.id}`, { replaceUrl: true });
          }
          this.message.set('Daten synchronisiert');
        },
        error: (error: ApplicationError) => {
          if (generation !== this.refreshGeneration || this.roundContext.roundId() !== roundId) {
            return;
          }
          this.masterDataError.set(true);
          if (error.kind === 'unauthenticated') {
            this.auth.markAnonymous();
            return;
          }
          this.message.set('Synchronisierung nicht möglich');
          this.feedback.notify(
            'error',
            'Synchronisierung nicht möglich',
            'Prüfen Sie Ihre Verbindung und versuchen Sie es erneut.',
          );
        },
      });
  }

  selectCommittee(id: number | null): void {
    this.selectedCommitteeId.set(id);
  }

  selectExamRound(id: number): void {
    this.roundContext.select(id);
    this.refresh();
    void this.router.navigateByUrl('/dashboard');
  }
}
