import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { finalize } from 'rxjs';

import { ApplicationError } from '../application/application-error';
import { RoundContextService } from '../api/round-context.service';
import { AuthService } from '../auth/auth.service';
import { SessionScopeService } from '../auth/session-scope.service';
import type { Location } from '../api/master-data.models';
import { DASHBOARD_PROJECTION_PORT, type DashboardProjection } from './dashboard-projection.port';

/** Independent dashboard projection and loading/error state. */
@Injectable({ providedIn: 'root' })
export class DashboardProjectionService {
  private readonly port = inject(DASHBOARD_PROJECTION_PORT);
  private readonly auth = inject(AuthService);
  private readonly sessionScope = inject(SessionScopeService);
  private readonly roundContext = inject(RoundContextService);
  private readonly router = inject(Router);
  private generation = 0;
  private locationGeneration = 0;

  readonly projection = signal<DashboardProjection | null>(null);
  readonly loading = signal(false);
  readonly error = signal(false);
  readonly locationRefreshError = signal(false);

  constructor() {
    this.sessionScope.changes$.subscribe(() => this.clear());
    this.roundContext.changes$.subscribe(() => this.refresh());
  }

  refresh(): void {
    if (this.auth.state() !== 'authenticated') return;
    const roundId = this.roundContext.roundId();
    const generation = ++this.generation;
    const sessionGeneration = this.sessionScope.generation();
    if (this.projection()?.round.id !== roundId) this.projection.set(null);
    this.loading.set(true);
    this.error.set(false);

    this.sessionScope
      .forCurrentSession(this.port.load(roundId))
      .pipe(
        finalize(() => {
          if (generation === this.generation) this.loading.set(false);
        }),
      )
      .subscribe({
        next: (projection) => {
          if (!this.isCurrent(generation, sessionGeneration, roundId)) return;
          this.projection.set(projection);
          if (
            this.router.url.startsWith('/scheduling-overview/') &&
            projection.round.status === 'plan_confirmed'
          ) {
            void this.router.navigateByUrl(`/confirmed-plans/${projection.round.id}`, {
              replaceUrl: true,
            });
          }
        },
        error: (error: ApplicationError) => {
          if (!this.isCurrent(generation, sessionGeneration, roundId)) return;
          this.error.set(true);
          if (error.kind === 'unauthenticated') this.auth.markAnonymous();
        },
      });
  }

  /** Refreshes only venue/room references in an already loaded dashboard board. */
  refreshLocations(): void {
    if (!this.projection()) return;
    const roundId = this.roundContext.roundId();
    const generation = ++this.locationGeneration;
    const sessionGeneration = this.sessionScope.generation();
    this.locationRefreshError.set(false);
    this.sessionScope.forCurrentSession(this.port.loadLocations()).subscribe({
      next: (locations) => {
        if (
          generation !== this.locationGeneration ||
          sessionGeneration !== this.sessionScope.generation() ||
          roundId !== this.roundContext.roundId()
        ) {
          return;
        }
        this.applyLocations(locations);
      },
      error: (error: ApplicationError) => {
        if (
          generation !== this.locationGeneration ||
          sessionGeneration !== this.sessionScope.generation() ||
          roundId !== this.roundContext.roundId()
        ) {
          return;
        }
        this.locationRefreshError.set(true);
        if (error.kind === 'unauthenticated') this.auth.markAnonymous();
      },
    });
  }

  applyLocations(locations: Location[]): void {
    const current = this.projection();
    if (!current) return;
    const byId = new Map(locations.map((location) => [location.id, location]));
    this.projection.set({
      ...current,
      board: {
        ...current.board,
        locations,
        days: current.board.days.map((item) => ({
          ...item,
          location: byId.get(item.day.location_id),
        })),
      },
    });
  }

  private isCurrent(generation: number, sessionGeneration: number, roundId: number): boolean {
    return (
      generation === this.generation &&
      sessionGeneration === this.sessionScope.generation() &&
      roundId === this.roundContext.roundId()
    );
  }

  private clear(): void {
    this.generation += 1;
    this.locationGeneration += 1;
    this.projection.set(null);
    this.loading.set(false);
    this.error.set(false);
    this.locationRefreshError.set(false);
  }
}
