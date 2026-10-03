import { Injectable, inject, signal } from '@angular/core';
import { finalize } from 'rxjs';

import { ApplicationError } from '../application/application-error';
import { PlanningWriteEventsService } from '../application/planning-write-events.service';
import { RoundContextService } from '../api/round-context.service';
import { AuthService } from '../auth/auth.service';
import { SessionScopeService } from '../auth/session-scope.service';
import {
  APPLICATION_SHELL_CONTEXT_PORT,
  type ApplicationShellContext,
} from './application-shell-context.port';

/** Minimal shell labels and version, loaded independently from feature projections. */
@Injectable({ providedIn: 'root' })
export class ApplicationShellContextService {
  private readonly port = inject(APPLICATION_SHELL_CONTEXT_PORT);
  private readonly auth = inject(AuthService);
  private readonly sessionScope = inject(SessionScopeService);
  private readonly roundContext = inject(RoundContextService);
  private readonly writeEvents = inject(PlanningWriteEventsService);
  private generation = 0;

  readonly context = signal<ApplicationShellContext | null>(null);
  readonly loading = signal(false);
  readonly error = signal(false);

  constructor() {
    this.sessionScope.changes$.subscribe(() => {
      this.generation += 1;
      this.context.set(null);
      this.loading.set(false);
      this.error.set(false);
    });
    this.roundContext.changes$.subscribe(() => this.refresh());
    this.writeEvents.committed$.subscribe(({ sourceRoundId, scope, phase }) => {
      if (
        phase !== 'partial' ||
        scope !== 'round' ||
        this.roundContext.roundId() !== sourceRoundId
      ) {
        return;
      }
      this.refresh();
    });
  }

  refresh(): void {
    if (this.auth.state() !== 'authenticated') return;
    const roundId = this.roundContext.roundId();
    const generation = ++this.generation;
    const sessionGeneration = this.sessionScope.generation();
    if (this.context()?.roundId !== roundId) this.context.set(null);
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
        next: (context) => {
          if (!this.isCurrent(generation, sessionGeneration, roundId)) return;
          this.context.set(context);
        },
        error: (error: ApplicationError) => {
          if (!this.isCurrent(generation, sessionGeneration, roundId)) return;
          this.error.set(true);
          if (error.kind === 'unauthenticated') this.auth.markAnonymous();
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
}
