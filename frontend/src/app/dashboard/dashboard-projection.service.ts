import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Subscription, finalize } from 'rxjs';

import { ApplicationError } from '../application/application-error';
import { PlanningWriteEventsService } from '../application/planning-write-events.service';
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
  private readonly writeEvents = inject(PlanningWriteEventsService);
  private readonly router = inject(Router);
  private active = false;
  private fullRead: Subscription | null = null;
  private locationRead: Subscription | null = null;
  private candidateReferenceRead: Subscription | null = null;
  private committeeMemberRead: Subscription | null = null;
  private generation = 0;
  private locationGeneration = 0;
  private candidateReferenceGeneration = 0;
  private committeeMemberGeneration = 0;
  private loadingRoundId: number | null = null;
  private loadingSessionGeneration: number | null = null;
  private locationRevision = 0;
  private candidateReferenceRevision = 0;
  private committeeMemberRevision = 0;
  private latestLocations: {
    revision: number;
    roundId: number;
    sessionGeneration: number;
    locations: Location[];
  } | null = null;
  private latestCandidateReferences: {
    revision: number;
    roundId: number;
    sessionGeneration: number;
    candidates: DashboardProjection['board']['candidates'];
    summary: DashboardProjection['summary'];
  } | null = null;
  private latestCommitteeMembers: {
    revision: number;
    roundId: number;
    sessionGeneration: number;
    members: DashboardProjection['board']['members'];
  } | null = null;

  readonly projection = signal<DashboardProjection | null>(null);
  readonly loading = signal(false);
  readonly error = signal(false);
  readonly locationRefreshError = signal(false);
  readonly candidateRefreshLoading = signal(false);
  readonly candidateRefreshError = signal(false);
  readonly committeeRefreshLoading = signal(false);
  readonly committeeRefreshError = signal(false);

  constructor() {
    this.sessionScope.changes$.subscribe(() => this.clear());
    this.roundContext.changes$.subscribe(() => {
      if (!this.active) return;
      this.cancelTargetedReads();
      this.refresh();
    });
    this.writeEvents.committed$.subscribe((roundId) => {
      if (!this.active || this.roundContext.roundId() !== roundId) return;
      this.cancelTargetedReads();
      this.refresh(true);
    });
  }

  activate(): void {
    this.active = true;
    this.refresh();
  }

  deactivate(): void {
    if (!this.active) return;
    this.active = false;
    this.clear();
  }

  refresh(force = false): void {
    if (!this.active || this.auth.state() !== 'authenticated') return;
    const roundId = this.roundContext.roundId();
    const sessionGeneration = this.sessionScope.generation();
    if (
      this.loading() &&
      !force &&
      this.loadingRoundId === roundId &&
      this.loadingSessionGeneration === sessionGeneration
    )
      return;
    const generation = ++this.generation;
    this.fullRead?.unsubscribe();
    const locationRevision = this.locationRevision;
    const candidateReferenceRevision = this.candidateReferenceRevision;
    const committeeMemberRevision = this.committeeMemberRevision;
    this.loadingRoundId = roundId;
    this.loadingSessionGeneration = sessionGeneration;
    if (this.projection()?.round.id !== roundId) this.projection.set(null);
    this.loading.set(true);
    this.error.set(false);

    this.fullRead = this.sessionScope
      .forCurrentSession(this.port.load(roundId))
      .pipe(
        finalize(() => {
          if (generation === this.generation) this.loading.set(false);
        }),
      )
      .subscribe({
        next: (projection) => {
          if (!this.isCurrent(generation, sessionGeneration, roundId)) return;
          const latestLocations = this.latestLocations;
          const currentProjection =
            latestLocations &&
            latestLocations.revision > locationRevision &&
            latestLocations.roundId === roundId &&
            latestLocations.sessionGeneration === sessionGeneration
              ? withLocations(projection, latestLocations.locations)
              : projection;
          const latestCandidateReferences = this.latestCandidateReferences;
          const projectionWithCandidates =
            latestCandidateReferences &&
            latestCandidateReferences.revision > candidateReferenceRevision &&
            latestCandidateReferences.roundId === roundId &&
            latestCandidateReferences.sessionGeneration === sessionGeneration
              ? {
                  ...currentProjection,
                  summary: latestCandidateReferences.summary,
                  board: {
                    ...currentProjection.board,
                    candidates: latestCandidateReferences.candidates,
                  },
                }
              : currentProjection;
          const latestCommitteeMembers = this.latestCommitteeMembers;
          const projectionWithMembers =
            latestCommitteeMembers &&
            latestCommitteeMembers.revision > committeeMemberRevision &&
            latestCommitteeMembers.roundId === roundId &&
            latestCommitteeMembers.sessionGeneration === sessionGeneration
              ? {
                  ...projectionWithCandidates,
                  board: {
                    ...projectionWithCandidates.board,
                    members: latestCommitteeMembers.members,
                  },
                }
              : projectionWithCandidates;
          this.projection.set(projectionWithMembers);
          this.locationRefreshError.set(false);
          this.candidateRefreshError.set(false);
          this.committeeRefreshError.set(false);
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
    if (!this.active || !this.projection()) return;
    const roundId = this.roundContext.roundId();
    const generation = ++this.locationGeneration;
    this.locationRead?.unsubscribe();
    const sessionGeneration = this.sessionScope.generation();
    this.locationRefreshError.set(false);
    this.locationRead = this.sessionScope.forCurrentSession(this.port.loadLocations()).subscribe({
      next: (locations) => {
        if (
          generation !== this.locationGeneration ||
          sessionGeneration !== this.sessionScope.generation() ||
          roundId !== this.roundContext.roundId()
        ) {
          return;
        }
        this.latestLocations = {
          revision: ++this.locationRevision,
          roundId,
          sessionGeneration,
          locations,
        };
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

  /** Refresh candidate references and the candidate count without reloading the board. */
  refreshCandidateReferences(): void {
    if (!this.active || !this.hasProjectionOrPendingLoad()) return;
    const roundId = this.roundContext.roundId();
    const generation = ++this.candidateReferenceGeneration;
    this.candidateReferenceRead?.unsubscribe();
    const sessionGeneration = this.sessionScope.generation();
    this.candidateRefreshLoading.set(true);
    this.candidateRefreshError.set(false);
    this.candidateReferenceRead = this.sessionScope
      .forCurrentSession(this.port.loadCandidateReferences(roundId))
      .pipe(
        finalize(() => {
          if (generation === this.candidateReferenceGeneration) {
            this.candidateRefreshLoading.set(false);
          }
        }),
      )
      .subscribe({
        next: ({ candidates, summary }) => {
          if (
            generation !== this.candidateReferenceGeneration ||
            sessionGeneration !== this.sessionScope.generation() ||
            roundId !== this.roundContext.roundId()
          )
            return;
          this.latestCandidateReferences = {
            revision: ++this.candidateReferenceRevision,
            roundId,
            sessionGeneration,
            candidates,
            summary,
          };
          const projection = this.projection();
          if (projection?.round.id === roundId) {
            this.projection.set({
              ...projection,
              summary,
              board: { ...projection.board, candidates },
            });
          }
        },
        error: (error: ApplicationError) => {
          if (
            generation !== this.candidateReferenceGeneration ||
            sessionGeneration !== this.sessionScope.generation() ||
            roundId !== this.roundContext.roundId()
          )
            return;
          this.candidateRefreshError.set(true);
          if (error.kind === 'unauthenticated') this.auth.markAnonymous();
        },
      });
  }

  /** Refresh committee member references without reloading the board. */
  refreshCommitteeMembers(): void {
    if (!this.active || !this.hasProjectionOrPendingLoad()) return;
    const roundId = this.roundContext.roundId();
    const generation = ++this.committeeMemberGeneration;
    this.committeeMemberRead?.unsubscribe();
    const sessionGeneration = this.sessionScope.generation();
    this.committeeRefreshLoading.set(true);
    this.committeeRefreshError.set(false);
    this.committeeMemberRead = this.sessionScope
      .forCurrentSession(this.port.loadCommitteeMembers())
      .pipe(
        finalize(() => {
          if (generation === this.committeeMemberGeneration) {
            this.committeeRefreshLoading.set(false);
          }
        }),
      )
      .subscribe({
        next: (members) => {
          if (
            generation !== this.committeeMemberGeneration ||
            sessionGeneration !== this.sessionScope.generation() ||
            roundId !== this.roundContext.roundId()
          )
            return;
          this.latestCommitteeMembers = {
            revision: ++this.committeeMemberRevision,
            roundId,
            sessionGeneration,
            members,
          };
          const projection = this.projection();
          if (projection?.round.id === roundId) {
            this.projection.set({
              ...projection,
              board: { ...projection.board, members },
            });
          }
        },
        error: (error: ApplicationError) => {
          if (
            generation !== this.committeeMemberGeneration ||
            sessionGeneration !== this.sessionScope.generation() ||
            roundId !== this.roundContext.roundId()
          )
            return;
          this.committeeRefreshError.set(true);
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
    this.fullRead?.unsubscribe();
    this.cancelTargetedReads();
    this.fullRead = null;
    this.latestLocations = null;
    this.latestCandidateReferences = null;
    this.latestCommitteeMembers = null;
    this.loadingRoundId = null;
    this.loadingSessionGeneration = null;
    this.projection.set(null);
    this.loading.set(false);
    this.error.set(false);
    this.locationRefreshError.set(false);
    this.candidateRefreshError.set(false);
    this.committeeRefreshError.set(false);
    this.candidateRefreshLoading.set(false);
    this.committeeRefreshLoading.set(false);
  }

  private cancelTargetedReads(): void {
    this.locationGeneration += 1;
    this.candidateReferenceGeneration += 1;
    this.committeeMemberGeneration += 1;
    this.locationRead?.unsubscribe();
    this.candidateReferenceRead?.unsubscribe();
    this.committeeMemberRead?.unsubscribe();
    this.locationRead = null;
    this.candidateReferenceRead = null;
    this.committeeMemberRead = null;
    this.locationRefreshError.set(false);
    this.candidateRefreshError.set(false);
    this.committeeRefreshError.set(false);
    this.candidateRefreshLoading.set(false);
    this.committeeRefreshLoading.set(false);
  }

  private hasProjectionOrPendingLoad(): boolean {
    const roundId = this.roundContext.roundId();
    const sessionGeneration = this.sessionScope.generation();
    return (
      this.projection()?.round.id === roundId ||
      (this.loading() &&
        this.loadingRoundId === roundId &&
        this.loadingSessionGeneration === sessionGeneration)
    );
  }
}

function withLocations(
  projection: DashboardProjection,
  locations: Location[],
): DashboardProjection {
  const byId = new Map(locations.map((location) => [location.id, location]));
  return {
    ...projection,
    board: {
      ...projection.board,
      locations,
      days: projection.board.days.map((item) => ({
        ...item,
        location: byId.get(item.day.location_id),
      })),
    },
  };
}
