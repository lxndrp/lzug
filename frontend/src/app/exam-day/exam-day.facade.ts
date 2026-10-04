import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { Observable } from 'rxjs';

import { ApplicationError } from '../application/application-error';
import { AuthService } from '../auth/auth.service';
import { SessionScopeService } from '../auth/session-scope.service';
import { PersonalFacade } from '../personal/personal.facade';
import { EXAM_DAY_PORT } from './exam-day.port';
import type {
  CloseExamDayCommand,
  ConfirmedPlanDayView,
  ExamDayClosure,
  ExamDayReopeningImpact,
  ExamDayReopeningScope,
  ReopenExamDayCommand,
  SaveAttendanceCommand,
  UpdateExecutionStatusCommand,
} from './exam-day.models';

export type ExamDayViewState = 'loading' | 'ready' | 'error' | 'not-found';
type ExamDayContext = {
  roundId: number | null;
  dayId: number;
  contextSequence: number;
  sessionGeneration: number;
};

/** Owns the selected examination day and its view-scoped read and command lifecycle. */
@Injectable()
export class ExamDayFacade {
  private readonly port = inject(EXAM_DAY_PORT);
  private readonly personal = inject(PersonalFacade);
  private readonly auth = inject(AuthService);
  private readonly sessionScope = inject(SessionScopeService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly state = signal<ExamDayViewState>('loading');
  readonly view = signal<ConfirmedPlanDayView | null>(null);
  readonly actionMessage = signal<string | null>(null);
  readonly actionError = signal<string | null>(null);
  readonly embeddedActionError = signal<string | null>(null);
  readonly savingKeys = signal<Set<string>>(new Set());
  readonly reopeningImpact = signal<ExamDayReopeningImpact | null>(null);
  readonly contextGeneration = signal(0);

  private roundId: number | null = null;
  private dayId: number | null = null;
  private hasBoundContext = false;
  private requestSequence = 0;
  private contextSequence = 0;
  private previewSequence = 0;

  constructor() {
    this.sessionScope.changes$
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.onSessionChange());
    this.destroyRef.onDestroy(() => {
      this.contextSequence += 1;
    });
  }

  bindContext(roundId: number | null, dayId: number | null): void {
    if (this.hasBoundContext && this.roundId === roundId && this.dayId === dayId) return;
    this.hasBoundContext = true;
    this.roundId = roundId;
    this.dayId = dayId;
    this.contextSequence += 1;
    this.contextGeneration.update((generation) => generation + 1);
    this.embeddedActionError.set(null);
    this.load(true);
  }

  load(contextChanged = false): void {
    const requestSequence = ++this.requestSequence;
    const requestedDayId = this.dayId;
    const requestedRoundId = this.roundId;
    const contextSequence = this.contextSequence;
    const sessionGeneration = this.sessionScope.generation();
    this.actionMessage.set(null);
    this.actionError.set(null);
    this.previewSequence += 1;
    this.reopeningImpact.set(null);
    if (contextChanged) {
      this.savingKeys.set(new Set());
      this.view.set(null);
    } else {
      this.savingKeys.update((keys) => {
        const current = new Set(keys);
        current.delete('day-reopening-impact');
        return current;
      });
    }

    if (requestedDayId === null) {
      this.view.set(null);
      this.state.set('not-found');
      return;
    }

    this.state.set('loading');
    this.sessionScope.forCurrentSession(this.port.getConfirmedPlanDay(requestedDayId)).subscribe({
      next: (view) => {
        if (
          !this.isCurrent(
            requestSequence,
            contextSequence,
            sessionGeneration,
            requestedDayId,
            requestedRoundId,
          )
        ) {
          return;
        }
        if (requestedRoundId !== null && view.plan.id !== requestedRoundId) {
          this.view.set(null);
          this.state.set('not-found');
          return;
        }
        this.view.set(view);
        this.embeddedActionError.set(null);
        this.state.set('ready');
      },
      error: (error: ApplicationError) => {
        if (
          !this.isCurrent(
            requestSequence,
            contextSequence,
            sessionGeneration,
            requestedDayId,
            requestedRoundId,
          )
        ) {
          return;
        }
        if (contextChanged) this.view.set(null);
        this.state.set(error.kind === 'not-found' ? 'not-found' : 'error');
      },
    });
  }

  private saveAction(key: string, request: Observable<ConfirmedPlanDayView>): void {
    if (this.hasSavingAction()) return;
    const context = this.captureContext();
    if (!context) return;
    this.savingKeys.set(new Set([key]));
    this.actionMessage.set(null);
    this.actionError.set(null);
    request.subscribe({
      next: (view) => {
        if (!this.isActionContextCurrent(context)) return;
        if (
          view.day.id !== context.dayId ||
          (context.roundId !== null && view.plan.id !== context.roundId)
        ) {
          this.savingKeys.set(new Set());
          this.actionError.set('Die Tagesantwort gehört nicht mehr zum geöffneten Prüfungstag.');
          return;
        }
        this.requestSequence += 1;
        this.view.set(view);
        this.savingKeys.set(new Set());
        this.state.set('ready');
        this.actionMessage.set('Änderung gespeichert.');
      },
      error: (error: ApplicationError) => {
        if (!this.isActionContextCurrent(context)) return;
        this.savingKeys.set(new Set());
        this.actionError.set(
          this.applicationError(error, 'Die Änderung konnte nicht gespeichert werden.'),
        );
      },
    });
  }

  saveCandidateAttendance(command: SaveAttendanceCommand): void {
    if (command.dayId !== this.dayId) return;
    this.saveAction(`candidate-${command.entityId}`, this.port.saveCandidateAttendance(command));
  }

  saveMemberAttendance(command: SaveAttendanceCommand): void {
    if (command.dayId !== this.dayId) return;
    this.saveAction(`member-${command.entityId}`, this.port.saveMemberAttendance(command));
  }

  startExamSlot(
    dayId: number,
    slotId: number,
    actualStartedAt: string | null,
    dayRevision?: number,
  ): void {
    if (dayId !== this.dayId) return;
    this.saveAction(
      `start-${slotId}`,
      this.port.startExamSlot(dayId, slotId, actualStartedAt, dayRevision),
    );
  }

  updateExamSlotStatus(command: UpdateExecutionStatusCommand): void {
    if (command.dayId !== this.dayId) return;
    this.saveAction(`execution-${command.slotId}`, this.port.updateExamSlotStatus(command));
  }

  closeExamDay(command: CloseExamDayCommand, successMessage: string): void {
    if (command.dayId !== this.dayId) return;
    this.runClosureAction('day-close', this.port.closeExamDay(command), successMessage);
  }

  reopenExamDay(command: ReopenExamDayCommand, successMessage: string): void {
    if (command.dayId !== this.dayId) return;
    this.runClosureAction('day-reopen', this.port.reopenExamDay(command), successMessage);
  }

  private runClosureAction(
    key: string,
    request: Observable<ExamDayClosure>,
    successMessage: string,
  ): void {
    if (this.hasSavingAction()) return;
    const context = this.captureContext();
    if (!context) return;
    this.savingKeys.set(new Set([key]));
    this.actionMessage.set(null);
    this.actionError.set(null);
    request.subscribe({
      next: (closure) => {
        if (!this.isActionContextCurrent(context)) return;
        if (closure.dayId !== context.dayId) {
          this.savingKeys.set(new Set());
          this.actionError.set('Die Abschlussantwort gehört nicht mehr zum geöffneten Tag.');
          return;
        }
        this.requestSequence += 1;
        this.savingKeys.set(new Set());
        this.reopeningImpact.set(null);
        this.view.update((current) =>
          current
            ? {
                ...current,
                day: {
                  ...current.day,
                  revision: closure.revision,
                  closureStatus: closure.status,
                  closure,
                },
              }
            : current,
        );
        this.state.set('ready');
        this.actionMessage.set(successMessage);
      },
      error: (error: ApplicationError) => {
        if (!this.isActionContextCurrent(context)) return;
        this.savingKeys.set(new Set());
        this.actionError.set(
          this.applicationError(error, 'Die Abschlussaktion konnte nicht ausgeführt werden.'),
        );
      },
    });
  }

  previewReopening(dayId: number, scope: ExamDayReopeningScope[]): void {
    if (this.hasSavingAction()) return;
    const context = this.captureContext();
    if (!context || context.dayId !== dayId) return;
    const previewSequence = ++this.previewSequence;
    this.savingKeys.set(new Set(['day-reopening-impact']));
    this.actionError.set(null);
    this.port.previewExamDayReopening(dayId, scope).subscribe({
      next: (impact) => {
        if (
          !this.isActionContextCurrent(context) ||
          previewSequence !== this.previewSequence
        ) {
          return;
        }
        if (impact.dayId !== context.dayId) {
          this.savingKeys.set(new Set());
          this.actionError.set('Die Auswirkungsprüfung gehört nicht mehr zum geöffneten Tag.');
          return;
        }
        if (impact.revision !== this.view()?.day.revision) {
          this.savingKeys.set(new Set());
          this.reopeningImpact.set(null);
          this.actionError.set('Die Auswirkungsprüfung gehört nicht mehr zum aktuellen Stand.');
          return;
        }
        this.savingKeys.set(new Set());
        this.reopeningImpact.set(impact);
      },
      error: (error: ApplicationError) => {
        if (
          !this.isActionContextCurrent(context) ||
          previewSequence !== this.previewSequence
        ) {
          return;
        }
        this.savingKeys.set(new Set());
        this.actionError.set(
          this.applicationError(error, 'Die Auswirkungen konnten nicht ermittelt werden.'),
        );
      },
    });
  }

  reportAbsence(dayId: number, assignmentId: number, dayRevision: number | undefined): void {
    if (this.hasSavingAction()) return;
    const context = this.captureContext();
    if (!context || context.dayId !== dayId) return;
    this.savingKeys.set(new Set([`absence-${assignmentId}`]));
    this.actionMessage.set(null);
    this.actionError.set(null);
    this.personal
      .createAbsenceReport({ examDayId: dayId, assignmentId, dayRevision })
      .subscribe({
        next: () => {
          if (!this.isActionContextCurrent(context)) return;
          this.savingKeys.set(new Set());
          this.actionMessage.set('Ausfallmeldung gespeichert.');
          void this.router.navigateByUrl(
            this.auth.session()?.demo_role ? '/demo-scenarios' : '/absence-reports',
          );
        },
        error: (error: ApplicationError) => {
          if (!this.isActionContextCurrent(context)) return;
          this.savingKeys.set(new Set());
          this.actionError.set(
            this.applicationError(error, 'Die Ausfallmeldung konnte nicht gespeichert werden.'),
          );
        },
      });
  }

  refreshAfterEmbeddedMutation(dayId: number, minimumRevision?: number): void {
    if (this.dayId !== dayId || this.roundId === null) return;
    this.previewSequence += 1;
    this.reopeningImpact.set(null);
    this.savingKeys.update((keys) => {
      const current = new Set(keys);
      current.delete('day-reopening-impact');
      return current;
    });
    const requestSequence = ++this.requestSequence;
    const contextSequence = this.contextSequence;
    const sessionGeneration = this.sessionScope.generation();
    const roundId = this.roundId;
    this.actionError.set(null);
    this.state.set('loading');
    this.sessionScope.forCurrentSession(this.port.getConfirmedPlanDay(dayId)).subscribe({
      next: (view) => {
        if (!this.isCurrent(requestSequence, contextSequence, sessionGeneration, dayId, roundId)) {
          return;
        }
        if (view.plan.id !== roundId) {
          this.state.set('not-found');
          return;
        }
        if (minimumRevision !== undefined && view.day.revision < minimumRevision) {
          this.state.set('error');
          this.actionError.set(
            'Die aktualisierten Tagesdaten entsprechen nicht der akzeptierten Revision.',
          );
          return;
        }
        this.view.set(view);
        this.embeddedActionError.set(null);
        this.state.set('ready');
      },
      error: () => {
        if (!this.isCurrent(requestSequence, contextSequence, sessionGeneration, dayId, roundId)) {
          return;
        }
        this.state.set('error');
        this.actionError.set(
          'Die Änderung wurde gespeichert, aber die aktuelle Tagesansicht konnte ' +
            'nicht geladen werden.',
        );
      },
    });
  }

  hasSavingAction(): boolean {
    return this.savingKeys().size > 0;
  }

  showValidationError(message: string): void {
    this.actionMessage.set(null);
    this.actionError.set(message);
  }

  showEmbeddedActionError(message: string): void {
    this.embeddedActionError.set(message);
  }

  private onSessionChange(): void {
    this.contextSequence += 1;
    this.contextGeneration.update((generation) => generation + 1);
    this.requestSequence += 1;
    this.previewSequence += 1;
    this.view.set(null);
    this.actionMessage.set(null);
    this.actionError.set(null);
    this.embeddedActionError.set(null);
    this.savingKeys.set(new Set());
    this.reopeningImpact.set(null);
    if (this.dayId === null) {
      this.state.set('not-found');
      return;
    }
    this.contextSequence += 1;
    this.load(true);
  }

  private captureContext(): ExamDayContext | null {
    if (this.dayId === null || !this.view()) return null;
    return {
      roundId: this.roundId,
      dayId: this.dayId,
      contextSequence: this.contextSequence,
      sessionGeneration: this.sessionScope.generation(),
    };
  }

  private isActionContextCurrent(context: ExamDayContext): boolean {
    return (
      context.contextSequence === this.contextSequence &&
      context.dayId === this.dayId &&
      context.roundId === this.roundId &&
      context.sessionGeneration === this.sessionScope.generation()
    );
  }

  private isCurrent(
    requestSequence: number,
    contextSequence: number,
    sessionGeneration: number,
    dayId: number,
    roundId: number | null,
  ): boolean {
    return (
      requestSequence === this.requestSequence &&
      contextSequence === this.contextSequence &&
      sessionGeneration === this.sessionScope.generation() &&
      this.dayId === dayId &&
      this.roundId === roundId
    );
  }

  private applicationError(error: ApplicationError, fallback: string): string {
    return error.message || fallback;
  }
}
