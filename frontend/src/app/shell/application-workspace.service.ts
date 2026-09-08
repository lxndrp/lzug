import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { finalize } from 'rxjs';

import type { ExamRound, MasterData, PlanningBoard, RoundSummary } from '../api/api.models';
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

  refresh(): void {
    if (this.auth.state() !== 'authenticated') return;
    this.loading.set(true);
    this.api
      .refreshDashboard()
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: ({ root, round, summary, board, masterData }) => {
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
        error: (error: { status?: number }) => {
          this.masterDataError.set(true);
          if (error.status === 401) {
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
