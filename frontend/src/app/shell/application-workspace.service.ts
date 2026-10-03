import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { finalize } from 'rxjs';

import { ApplicationError } from '../application/application-error';
import { RoundContextService } from '../api/round-context.service';
import { AuthService } from '../auth/auth.service';
import { SessionScopeService } from '../auth/session-scope.service';
import { UiFeedbackService } from './ui-feedback.service';
import type { Location } from '../api/master-data.models';
import { WORKSPACE_PORT, type WorkspaceSnapshot } from './workspace.port';

/** Coherent application-wide read state shared by shell and feature coordinators. */
@Injectable({ providedIn: 'root' })
export class ApplicationWorkspaceService {
  private readonly workspacePort = inject(WORKSPACE_PORT);
  private readonly auth = inject(AuthService);
  private readonly sessionScope = inject(SessionScopeService);
  private readonly feedback = inject(UiFeedbackService);
  private readonly roundContext = inject(RoundContextService);
  private readonly router = inject(Router);

  readonly round = signal<WorkspaceSnapshot['round'] | null>(null);
  readonly summary = signal<WorkspaceSnapshot['summary'] | null>(null);
  readonly board = signal<WorkspaceSnapshot['board'] | null>(null);
  readonly masterData = signal<WorkspaceSnapshot['masterData'] | null>(null);
  readonly message = signal('Bereit');
  readonly loading = signal(false);
  readonly actionBusy = signal(false);
  readonly applicationVersion = signal<string | null>(null);
  readonly masterDataError = signal(false);
  private refreshGeneration = 0;
  private locationRefreshGeneration = 0;

  constructor() {
    this.sessionScope.changes$.subscribe(() => this.clear());
  }

  refresh(): void {
    if (this.auth.state() !== 'authenticated') return;
    const roundId = this.roundContext.roundId();
    const generation = ++this.refreshGeneration;
    const sessionGeneration = this.sessionScope.generation();
    if (this.round() && this.round()?.id !== roundId) {
      this.round.set(null);
      this.summary.set(null);
      this.board.set(null);
      this.masterData.set(null);
    }
    this.masterDataError.set(false);
    this.loading.set(true);
    this.sessionScope
      .forCurrentSession(this.workspacePort.loadDashboard(roundId))
      .pipe(
        finalize(() => {
          if (generation === this.refreshGeneration) this.loading.set(false);
        }),
      )
      .subscribe({
        next: ({ applicationVersion, round, summary, board, masterData }) => {
          if (
            generation !== this.refreshGeneration ||
            sessionGeneration !== this.sessionScope.generation() ||
            this.roundContext.roundId() !== roundId
          ) {
            return;
          }
          this.masterDataError.set(false);
          this.applicationVersion.set(applicationVersion);
          this.round.set(round);
          this.summary.set(summary);
          this.board.set(board);
          this.masterData.set(masterData);
          if (
            this.router.url.startsWith('/scheduling-overview/') &&
            round.status === 'plan_confirmed'
          ) {
            void this.router.navigateByUrl(`/confirmed-plans/${round.id}`, { replaceUrl: true });
          }
          this.message.set('Daten synchronisiert');
        },
        error: (error: ApplicationError) => {
          if (
            generation !== this.refreshGeneration ||
            sessionGeneration !== this.sessionScope.generation() ||
            this.roundContext.roundId() !== roundId
          ) {
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

  /** Refresh only locations in the transitional planning workspace. */
  refreshLocations(): void {
    if (!this.board() && !this.masterData()) return;
    const roundId = this.roundContext.roundId();
    const generation = ++this.locationRefreshGeneration;
    const sessionGeneration = this.sessionScope.generation();
    this.sessionScope.forCurrentSession(this.workspacePort.loadLocations()).subscribe({
      next: (locations) => {
        if (
          generation !== this.locationRefreshGeneration ||
          sessionGeneration !== this.sessionScope.generation() ||
          roundId !== this.roundContext.roundId()
        )
          return;
        const board = this.board();
        if (board) this.board.set(withLocations(board, locations));
        const masterData = this.masterData();
        if (masterData) this.masterData.set({ ...masterData, locations });
      },
      error: (error: ApplicationError) => {
        if (
          generation !== this.locationRefreshGeneration ||
          sessionGeneration !== this.sessionScope.generation() ||
          roundId !== this.roundContext.roundId()
        ) {
          return;
        }
        if (error.kind === 'unauthenticated') this.auth.markAnonymous();
        else {
          this.feedback.notify(
            'error',
            'Prüfungsorte nicht aktualisiert',
            'Die angezeigten Planungsdaten bleiben erhalten. Bitte erneut laden.',
          );
        }
      },
    });
  }

  selectExamRound(id: number): void {
    this.roundContext.select(id);
    this.refresh();
    void this.router.navigateByUrl('/dashboard');
  }

  private clear(): void {
    this.refreshGeneration += 1;
    this.locationRefreshGeneration += 1;
    this.round.set(null);
    this.summary.set(null);
    this.board.set(null);
    this.masterData.set(null);
    this.message.set('Bereit');
    this.loading.set(false);
    this.actionBusy.set(false);
    this.applicationVersion.set(null);
    this.masterDataError.set(false);
  }
}

function withLocations<T extends WorkspaceSnapshot['board']>(board: T, locations: Location[]): T {
  const byId = new Map(locations.map((location) => [location.id, location]));
  return {
    ...board,
    locations,
    days: board.days.map((item) => ({
      ...item,
      location: byId.get(item.day.location_id),
    })),
  };
}
