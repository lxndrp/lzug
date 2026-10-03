import { computed, effect, Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import {
  EMPTY,
  NEVER,
  Subject,
  Subscription,
  defer,
  catchError,
  filter,
  finalize,
  of,
  switchMap,
  tap,
  takeUntil,
  throwError,
} from 'rxjs';

import type {
  AvailabilityRequest,
  CandidateDayGenerationResult,
  CandidateExamDay,
  EditablePlanningProposal,
  PlanningResult,
  PlanningValidationViolation,
  PlanningRoundUpdate,
  PlanningSnapshot,
} from './planning.models';
import { ApplicationError } from '../application/application-error';
import { PlanningWriteEventsService } from '../application/planning-write-events.service';
import { ReferenceDataWriteEventsService } from '../application/reference-data-write-events.service';
import { RoundContextService } from '../api/round-context.service';
import { AuthService } from '../auth/auth.service';
import { SessionScopeService } from '../auth/session-scope.service';
import type {
  AvailabilityPayload,
  CandidateExamDayPayload,
  PlanningSettingsPayload,
  PlanningViewEffect,
  PlanningViewEffectCommand,
} from './planning-view-effect';
import type { ProposalEditorState } from './planning-proposal-editor.component';
import { UiFeedbackService } from '../shell/ui-feedback.service';
import { PLANNING_PORT } from './planning.port';

/** Planning commands and editor state for the selected examination round. */
@Injectable({ providedIn: 'root' })
export class PlanningWorkflowService {
  private readonly planning = inject(PLANNING_PORT);
  private readonly auth = inject(AuthService);
  private readonly sessionScope = inject(SessionScopeService);
  private readonly feedback = inject(UiFeedbackService);
  private readonly roundContext = inject(RoundContextService);
  private readonly router = inject(Router);
  private readonly writeEvents = inject(PlanningWriteEventsService);
  private readonly referenceDataWrites = inject(ReferenceDataWriteEventsService);
  private readonly pending = signal(false);
  private activeView: symbol | null = null;
  private activeRoundId: number | null = null;
  private activeViewEnded: Subject<void> | null = null;
  private lastResultRoundId: number | null = null;
  private proposalLoad?: Subscription;
  private planningLoad?: Subscription;
  private planningGeneration = 0;
  private effectVersion = 0;
  private readonly pendingAvailability = new Set<string>();
  private acceptedProposalSaveGeneration = 0;
  private pendingProposalReload: { roundId: number; view: symbol | null } | null = null;

  readonly actionBusy = computed(() => this.pending());
  readonly snapshot = signal<PlanningSnapshot | null>(null);
  readonly loading = signal(false);
  readonly loadError = signal(false);
  readonly viewEffects = signal<PlanningViewEffect[]>([]);
  readonly lastResult = signal<PlanningResult | null>(null);
  readonly proposal = signal<EditablePlanningProposal | null>(null);
  readonly proposalSaveAcknowledgement = signal(0);
  readonly proposalReloadAcknowledgement = signal(0);
  readonly editorState = signal<ProposalEditorState>('idle');
  readonly editorError = signal<string | null>(null);
  readonly editorViolations = signal<PlanningValidationViolation[]>([]);
  readonly candidateDayGeneration = signal<CandidateDayGenerationResult | null>(null);
  readonly canGenerateCandidateDays = computed(
    () =>
      this.auth.hasCapability('planning-settings:write') &&
      this.auth.hasCapability('candidate-days:generate'),
  );
  readonly canCreateCandidateDay = computed(() => this.auth.hasCapability('candidate-days:create'));
  readonly canToggleCandidateDay = computed(() => this.auth.hasCapability('candidate-days:toggle'));

  constructor() {
    this.sessionScope.changes$.subscribe((change) => {
      this.resetForSessionChange();
      if (
        change.established &&
        this.auth.state() === 'authenticated' &&
        this.activeView &&
        this.activeRoundId !== null
      ) {
        this.loadPlanning(this.activeRoundId, this.activeView);
      }
    });
    effect(() => {
      const authenticated = this.auth.state() === 'authenticated';
      this.sessionScope.generation();
      const view = this.activeView;
      const roundId = this.activeRoundId;
      if (
        authenticated &&
        view &&
        roundId !== null &&
        !this.snapshot() &&
        !this.loading() &&
        !this.loadError()
      ) {
        this.loadPlanning(roundId, view);
      }
    });
    this.roundContext.changes$.subscribe(() => this.resetForRoundContextChange());
    this.referenceDataWrites.committed$.subscribe(() => {
      const roundId = this.activeRoundId;
      const view = this.activeView;
      if (roundId !== null && view && this.isSelectedRound(roundId)) {
        this.refreshPlanning(roundId);
      }
    });
    this.writeEvents.committed$.subscribe(({ sourceRoundId, scope, phase }) => {
      const activeRoundId = this.activeRoundId;
      if (
        phase === 'partial' &&
        scope === 'round' &&
        activeRoundId === sourceRoundId &&
        this.isSelectedRound(sourceRoundId)
      ) {
        // A staged command may have committed round-local data before its
        // follow-up fails. Refresh this feature without applying its response.
        this.refreshPlanning(sourceRoundId);
        return;
      }
      if (
        scope !== 'related-rounds' ||
        activeRoundId === null ||
        activeRoundId === sourceRoundId ||
        !this.isSelectedRound(activeRoundId)
      ) {
        return;
      }
      // Availability writes may be mirrored to another round for the same
      // member and half-year. The server owns that target set, so reload the
      // active round projection without applying the source response.
      this.refreshPlanning(activeRoundId);
    });
  }

  activateView(view: symbol, roundId: number): void {
    if (this.activeView === view && this.activeRoundId === roundId) {
      this.loadPlanning(roundId, view);
      return;
    }
    this.clearResultForRoundChange(roundId);
    this.endActiveView();
    this.activeView = view;
    this.activeRoundId = roundId;
    this.activeViewEnded = new Subject<void>();
    this.viewEffects.set([]);
    this.snapshot.set(null);
    this.resetPlanningState();
    this.loadPlanning(roundId, view);
  }

  deactivateView(view: symbol): void {
    if (this.activeView !== view) return;
    this.endActiveView();
    this.viewEffects.set([]);
    this.snapshot.set(null);
    this.activeRoundId = null;
    this.planningGeneration += 1;
    this.planningLoad?.unsubscribe();
    this.planningLoad = undefined;
    this.proposalLoad?.unsubscribe();
    this.proposalLoad = undefined;
    this.resetPlanningState();
    if (this.editorState() === 'loading' || this.editorState() === 'saving') {
      this.editorState.set('idle');
    }
  }

  private resetForSessionChange(): void {
    this.snapshot.set(null);
    this.loadError.set(false);
    this.lastResult.set(null);
    this.lastResultRoundId = null;
    this.candidateDayGeneration.set(null);
    this.resetPlanningProposal();
    this.editorError.set(null);
    this.editorViolations.set([]);
    this.planningGeneration += 1;
    this.planningLoad?.unsubscribe();
    this.planningLoad = undefined;
    this.loading.set(false);
  }

  private resetPlanningState(): void {
    this.candidateDayGeneration.set(null);
    this.resetPlanningProposal();
    this.editorError.set(null);
    this.editorViolations.set([]);
  }

  private loadPlanning(roundId: number, view: symbol): void {
    if (this.auth.state() !== 'authenticated') {
      this.loading.set(false);
      return;
    }
    const generation = ++this.planningGeneration;
    const sessionGeneration = this.sessionScope.generation();
    this.planningLoad?.unsubscribe();
    this.loading.set(true);
    this.loadError.set(false);
    this.planningLoad = this.sessionScope
      .forCurrentSession(this.planning.loadPlanning(roundId))
      .pipe(
        takeUntil(this.viewEnded(view)),
        finalize(() => {
          if (generation === this.planningGeneration) this.loading.set(false);
        }),
      )
      .subscribe({
        next: (snapshot) => {
          if (
            generation !== this.planningGeneration ||
            sessionGeneration !== this.sessionScope.generation() ||
            !this.isCurrentView(view) ||
            this.activeRoundId !== roundId ||
            this.roundContext.roundId() !== roundId
          )
            return;
          this.snapshot.set(snapshot);
          this.loadError.set(false);
          if (snapshot.round.status === 'plan_proposed') this.loadPlanningProposal(roundId, view);
          else this.resetPlanningProposal();
        },
        error: () => {
          if (generation !== this.planningGeneration || !this.isCurrentView(view)) return;
          this.loadError.set(true);
        },
      });
  }

  requestPlanConfirmation(roundId = this.captureRoundId(), view = this.activeView): void {
    if (!this.auth.hasCapability('planning-proposal:confirm')) {
      this.feedback.roleRestriction();
      return;
    }
    if (!this.ensurePlanningRound(roundId)) return;
    if (!this.beginOperation()) return;
    this.sessionScope
      .forCurrentSession(
        this.confirmForView(
          view,
          'Terminplan bestätigen?',
          'Der aktuelle Planungsvorschlag wird als verbindlicher Terminplan bestätigt.',
          'Plan verbindlich bestätigen',
        ),
      )
      .pipe(
        filter((confirmed) => confirmed && this.isCurrentView(view)),
        switchMap(() => defer(() => this.planning.confirmPlan(roundId))),
        finalize(() => this.pending.set(false)),
      )
      .subscribe({
        next: (result) => this.handlePlanConfirmation(result, roundId, view),
        error: () => this.reportPlanConfirmationFailure(roundId, view),
      });
  }

  savePlanningSettings(
    payload: PlanningSettingsPayload,
    roundId = this.captureRoundId(),
    view = this.activeView,
  ): void {
    if (!this.auth.hasCapability('planning-settings:write')) {
      this.feedback.roleRestriction();
      return;
    }
    if (!this.ensurePlanningRound(roundId)) return;
    if (!this.beginOperation()) return;
    this.sessionScope
      .forCurrentSession(this.planning.savePlanningSettings(payload, roundId))
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: () => {
          if (this.skipStaleWrite(roundId, view)) return;
          this.feedback.notify(
            'success',
            'Planungsrahmen gespeichert',
            'Die Änderungen sind übernommen.',
          );
          this.refreshPlanning(roundId);
        },
        error: () => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.feedback.notify(
            'error',
            'Planungsrahmen nicht gespeichert',
            'Bitte erneut versuchen.',
          );
        },
      });
  }

  saveExamRound(
    payload: PlanningRoundUpdate,
    roundId = this.captureRoundId(),
    view = this.activeView,
  ): void {
    if (!this.auth.hasCapability('round:write')) {
      this.feedback.roleRestriction();
      return;
    }
    if (!this.ensurePlanningRound(roundId)) return;
    if (!this.beginOperation()) return;
    this.sessionScope
      .forCurrentSession(this.planning.updateExamRound(payload, roundId))
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: () => {
          if (this.skipStaleWrite(roundId, view)) return;
          this.feedback.notify(
            'success',
            'Prüfungsrunde gespeichert',
            'Die Änderungen sind übernommen.',
          );
          this.refreshPlanning(roundId);
        },
        error: () => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.feedback.notify(
            'error',
            'Prüfungsrunde nicht gespeichert',
            'Bitte Eingaben prüfen.',
          );
        },
      });
  }

  requestAvailabilities(
    payload: AvailabilityRequest,
    roundId = this.captureRoundId(),
    view = this.activeView,
  ): void {
    if (!this.auth.hasCapability('availability:coordinate')) {
      this.feedback.roleRestriction();
      return;
    }
    if (!this.ensurePlanningRound(roundId)) return;
    if (!this.beginOperation()) return;
    let roundMetadataCommitted = false;
    this.sessionScope
      .forCurrentSession(
        this.planning.updateExamRound(payload, roundId).pipe(
          tap(() => (roundMetadataCommitted = true)),
          switchMap(() => this.planning.sendAvailabilityRequests(roundId)),
          catchError((error: unknown) => {
            if (roundMetadataCommitted) {
              this.writeEvents.notifyCommitted(roundId, 'round', 'partial');
            }
            return throwError(() => error);
          }),
        ),
      )
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: (result) => {
          if (this.skipStaleWrite(roundId, view)) return;
          this.feedback.notify(
            result.notification_warning ? 'error' : 'success',
            result.notification_warning
              ? 'Terminorganisation gestartet, Benachrichtigungen unvollständig'
              : 'Verfügbarkeiten angefragt',
            result.notification_warning ?? 'Die Terminorganisation ist jetzt in Abstimmung.',
          );
          this.refreshPlanning(roundId);
        },
        error: () => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.feedback.notify(
            'error',
            'Verfügbarkeiten nicht angefragt',
            'Gespeicherte Angaben bleiben erhalten. Bitte Voraussetzungen prüfen.',
          );
        },
      });
  }

  createCandidateDay(
    payload: CandidateExamDayPayload,
    roundId = this.captureRoundId(),
    view = this.activeView,
  ): void {
    if (!this.auth.hasCapability('candidate-days:create')) {
      this.feedback.roleRestriction();
      return;
    }
    if (!this.ensurePlanningRound(roundId)) return;
    if (!this.beginOperation()) return;
    this.sessionScope
      .forCurrentSession(this.planning.createCandidateExamDay(payload, roundId))
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: (day) => {
          if (this.skipStaleWrite(roundId, view)) return;
          this.emitViewEffect(view, { type: 'reset-candidate-day-draft' });
          this.feedback.notify('success', 'Prüfungstag angelegt', day.date);
          this.refreshPlanning(roundId);
        },
        error: () => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.feedback.notify(
            'error',
            'Prüfungstag nicht angelegt',
            'Die Eingabe bleibt erhalten. Bitte erneut versuchen.',
          );
        },
      });
  }

  generateCandidateDays(
    payload: PlanningSettingsPayload,
    roundId = this.captureRoundId(),
    view = this.activeView,
  ): void {
    if (!this.canGenerateCandidateDays()) {
      this.feedback.roleRestriction();
      return;
    }
    if (!this.ensurePlanningRound(roundId)) return;
    if (!this.beginOperation()) return;
    let settingsCommitted = false;
    this.sessionScope
      .forCurrentSession(
        this.planning.savePlanningSettings(payload, roundId).pipe(
          tap(() => (settingsCommitted = true)),
          switchMap(() => this.planning.generateCandidateExamDays(roundId)),
          catchError((error: unknown) => {
            if (settingsCommitted) this.writeEvents.notifyCommitted(roundId, 'round', 'partial');
            return throwError(() => error);
          }),
        ),
      )
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: (result) => {
          if (this.skipStaleWrite(roundId, view)) return;
          this.candidateDayGeneration.set(result);
          this.feedback.notify(
            'success',
            'Mögliche Prüfungstage berechnet',
            `${result.counts.created} angelegt, ${result.counts.existing} bereits vorhanden.`,
          );
          this.refreshPlanning(roundId);
        },
        error: () => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.feedback.notify(
            'error',
            'Prüfungstage nicht berechnet',
            'Planungszeitraum und Bundesland konnten nicht verarbeitet werden.',
          );
        },
      });
  }

  toggleCandidateDay(
    day: CandidateExamDay,
    roundId = this.captureRoundId(),
    view = this.activeView,
  ): void {
    if (!this.auth.hasCapability('candidate-days:toggle')) {
      this.feedback.roleRestriction();
      return;
    }
    if (!this.ensurePlanningRound(roundId)) return;
    const nextActive = day.is_active ? 0 : 1;
    if (!this.beginOperation()) return;
    this.sessionScope
      .forCurrentSession(
        this.planning.updateCandidateExamDay(day.id, { is_active: nextActive }, roundId),
      )
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: () => {
          if (this.skipStaleWrite(roundId, view)) return;
          this.feedback.notify(
            'success',
            `Prüfungstag ${nextActive ? 'aktiviert' : 'deaktiviert'}`,
            day.date,
          );
          this.refreshPlanning(roundId);
        },
        error: () => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.feedback.notify('error', 'Prüfungstag nicht geändert', 'Bitte erneut versuchen.');
        },
      });
  }

  saveAvailability(
    payload: AvailabilityPayload,
    roundId = this.captureRoundId(),
    view = this.activeView,
  ): void {
    const authSession = this.auth.session();
    const session = authSession?.demo_role ? authSession : null;
    const canSave =
      this.auth.hasCapability('availability:coordinate') ||
      this.auth.hasCapability('availability:write-own');
    if (
      !canSave ||
      (session?.demo_role === 'examiner' &&
        payload.committee_member_id !== session.committee_member_id)
    ) {
      this.feedback.roleRestriction();
      this.emitViewEffect(view, { type: 'availability-error', payload });
      return;
    }
    if (!this.ensurePlanningRound(roundId)) {
      this.emitViewEffect(view, { type: 'availability-error', payload, usePersistedValue: true });
      return;
    }
    const availabilityKey = `${payload.committee_member_id}:${payload.candidate_exam_day_id}`;
    if (this.pendingAvailability.has(availabilityKey)) return;
    this.pendingAvailability.add(availabilityKey);
    this.sessionScope
      .forCurrentSession(this.planning.saveMemberAvailability(payload, roundId))
      .pipe(finalize(() => this.pendingAvailability.delete(availabilityKey)))
      .subscribe({
        next: (availability) => {
          if (this.skipStaleWrite(roundId, view, 'related-rounds')) return;
          const refreshInFlight = this.loading();
          if (refreshInFlight) {
            this.planningGeneration += 1;
            this.planningLoad?.unsubscribe();
            this.planningLoad = undefined;
            this.loading.set(false);
          }
          this.snapshot.update((snapshot) =>
            snapshot
              ? {
                  ...snapshot,
                  board: {
                    ...snapshot.board,
                    availabilities: [
                      ...snapshot.board.availabilities.filter(
                        (item) =>
                          item.committee_member_id !== availability.committee_member_id ||
                          item.candidate_exam_day_id !== availability.candidate_exam_day_id,
                      ),
                      availability,
                    ],
                  },
                }
              : snapshot,
          );
          this.emitViewEffect(view, {
            type: 'availability-saved',
            payload,
            availability: availability.availability,
          });
          if (refreshInFlight) this.refreshPlanning(roundId);
        },
        error: () => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.emitViewEffect(view, { type: 'availability-error', payload });
          this.feedback.notify(
            'error',
            'Verfügbarkeit nicht gespeichert',
            'Die Auswahl wurde zurückgesetzt. Bitte erneut versuchen.',
          );
        },
      });
  }

  acknowledgeViewEffects(view: symbol, throughVersion: number): void {
    if (!this.isCurrentView(view)) return;
    this.viewEffects.update((effects) =>
      effects.filter((effect) => effect.version > throughVersion),
    );
  }

  generateProposal(roundId = this.captureRoundId(), view = this.activeView): void {
    if (!this.auth.hasCapability('planning-proposal:generate')) {
      this.feedback.roleRestriction();
      return;
    }
    if (!this.ensurePlanningRound(roundId)) return;
    if (!this.beginOperation()) return;
    this.sessionScope
      .forCurrentSession(this.planning.generateProposal(roundId))
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: (result) => {
          if (this.skipStaleWrite(roundId, view)) return;
          this.lastResult.set(result);
          this.lastResultRoundId = roundId;
          const planned = result.counts['planned_slots'] ?? 0;
          const suffix = result.validation?.passed === false ? ' mit Hinweisen' : '';
          this.feedback.notify(
            'success',
            'Planungsvorschlag erzeugt',
            `${planned} Termine${suffix}`,
          );
          this.refreshPlanning(roundId);
        },
        error: () => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.feedback.notify('error', 'Planung nicht erzeugt', 'Bitte Planungsdaten prüfen.');
        },
      });
  }

  confirmPlan(roundId = this.captureRoundId(), view = this.activeView): void {
    if (!this.auth.hasCapability('planning-proposal:confirm')) {
      this.feedback.roleRestriction();
      return;
    }
    if (!this.ensurePlanningRound(roundId)) return;
    if (!this.beginOperation()) return;
    this.submitPlanConfirmation(roundId, view);
  }

  loadPlanningProposal(roundId: number, view = this.activeView, explicitReload = false): void {
    if (!this.isCurrentView(view)) return;
    const acknowledgeReload =
      explicitReload ||
      (this.pendingProposalReload?.roundId === roundId && this.pendingProposalReload.view === view);
    this.proposalLoad?.unsubscribe();
    this.proposalLoad = undefined;
    if (
      this.snapshot()?.round.id !== roundId ||
      this.snapshot()?.round.status !== 'plan_proposed'
    ) {
      this.editorState.set('idle');
      return;
    }
    this.editorState.set('loading');
    this.editorError.set(null);
    this.editorViolations.set([]);
    const acceptedSaveGeneration = this.acceptedProposalSaveGeneration;
    const subscription = this.sessionScope
      .forCurrentSession(this.planning.getPlanningProposal(roundId))
      .pipe(
        takeUntil(this.viewEnded(view)),
        finalize(() => {
          if (this.isCurrentView(view) && this.editorState() === 'loading') {
            this.editorState.set('idle');
          }
        }),
      )
      .subscribe({
        next: (proposal) => {
          if (
            acceptedSaveGeneration !== this.acceptedProposalSaveGeneration ||
            !this.isSelectedRound(roundId) ||
            !this.isCurrentView(view)
          ) {
            return;
          }
          if (acknowledgeReload) {
            this.proposalReloadAcknowledgement.update((value) => value + 1);
            this.pendingProposalReload = null;
          }
          this.proposal.set(proposal);
          this.editorState.set('ready');
        },
        error: (error: ApplicationError) => {
          if (
            acceptedSaveGeneration !== this.acceptedProposalSaveGeneration ||
            !this.isSelectedRound(roundId) ||
            !this.isCurrentView(view)
          ) {
            return;
          }
          this.editorState.set('error');
          this.editorError.set(this.proposalErrorMessage(error));
          if (acknowledgeReload) this.pendingProposalReload = null;
        },
      });
    this.proposalLoad = subscription;
  }

  reloadPlanningProposal(roundId: number, view = this.activeView): void {
    if (this.activeRoundId === roundId) {
      this.pendingProposalReload = { roundId, view };
      this.loadPlanningProposal(roundId, view, true);
    }
  }

  savePlanningProposal(
    proposal: EditablePlanningProposal,
    roundId = this.captureRoundId(),
    view = this.activeView,
  ): void {
    if (!this.auth.hasCapability('planning-proposal:replace')) {
      this.feedback.roleRestriction();
      return;
    }
    if (!this.ensurePlanningRound(roundId) || proposal.round_id !== roundId) return;
    if (!this.beginOperation()) return;
    this.editorState.set('saving');
    this.editorError.set(null);
    this.editorViolations.set([]);
    const sourceRevision = proposal.revision;
    const command = { ...proposal, revision: sourceRevision };
    this.sessionScope
      .forCurrentSession(this.planning.savePlanningProposal(roundId, command))
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: (saved) => {
          if (this.isSelectedRound(roundId)) this.acceptedProposalSaveGeneration += 1;
          if (this.skipStaleWrite(roundId, view)) return;
          this.proposal.set(saved);
          this.proposalSaveAcknowledgement.update((value) => value + 1);
          this.editorState.set('ready');
          this.feedback.notify(
            'success',
            'Änderungen gespeichert',
            'Der Planungsvorschlag ist aktualisiert.',
          );
        },
        error: (error: ApplicationError) => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.editorState.set('error');
          const detail =
            typeof error.details === 'object' && error.details !== null
              ? (error.details as { violations?: PlanningValidationViolation[] })
              : undefined;
          this.editorViolations.set(detail?.violations ?? []);
          this.editorError.set(
            error.kind === 'conflict'
              ? 'Der Vorschlag wurde zwischenzeitlich geändert. Laden Sie die aktuelle Fassung, bevor Sie erneut speichern.'
              : this.proposalErrorMessage(error),
          );
        },
      });
  }

  private beginOperation(): boolean {
    if (this.pending()) return false;
    this.pending.set(true);
    return true;
  }

  private isCurrentView(view: symbol | null): boolean {
    return view === null || view === this.activeView;
  }

  private skipStaleWrite(
    roundId: number,
    view: symbol | null,
    scope: 'round' | 'related-rounds' = 'round',
  ): boolean {
    // This helper is called only from successful command responses. Publish
    // the commit independently of the initiating view so cross-round readers
    // can invalidate; response data and drafts remain fenced below.
    this.writeEvents.notifyCommitted(roundId, scope);
    if (!this.isSelectedRound(roundId)) return true;
    if (this.isCurrentView(view)) return false;

    // A command accepted by an older view may commit after the active view's
    // initial read. Reload only the matching active round and never apply the
    // old view's response or draft to the new projection.
    if (this.activeRoundId === roundId) {
      this.refreshPlanning(roundId);
    }
    return true;
  }

  private confirmForView(
    view: symbol | null,
    title: string,
    message: string,
    confirmLabel: string,
  ) {
    if (!this.isCurrentView(view)) return EMPTY;
    return this.feedback
      .confirm$(title, message, confirmLabel)
      .pipe(takeUntil(this.viewEnded(view)));
  }

  private viewEnded(view: symbol | null) {
    if (view === null) return NEVER;
    if (!this.isCurrentView(view)) return of(undefined);
    return this.activeViewEnded ?? of(undefined);
  }

  private endActiveView(): void {
    this.pendingProposalReload = null;
    this.activeView = null;
    this.activeViewEnded?.next();
    this.activeViewEnded?.complete();
    this.activeViewEnded = null;
  }

  private resetForRoundContextChange(): void {
    this.endActiveView();
    this.activeRoundId = null;
    this.planningGeneration += 1;
    this.planningLoad?.unsubscribe();
    this.planningLoad = undefined;
    this.proposalLoad?.unsubscribe();
    this.proposalLoad = undefined;
    this.loading.set(false);
    this.loadError.set(false);
    this.viewEffects.set([]);
    this.snapshot.set(null);
    this.lastResult.set(null);
    this.lastResultRoundId = null;
    this.resetPlanningState();
    if (this.editorState() === 'loading' || this.editorState() === 'saving') {
      this.editorState.set('idle');
    }
  }

  private emitViewEffect(view: symbol | null, effect: PlanningViewEffectCommand): void {
    if (!this.isCurrentView(view)) return;
    this.viewEffects.update((effects) => [
      ...effects,
      { ...effect, version: ++this.effectVersion } as PlanningViewEffect,
    ]);
  }

  private submitPlanConfirmation(roundId: number, view: symbol | null): void {
    this.sessionScope
      .forCurrentSession(defer(() => this.planning.confirmPlan(roundId)))
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: (result) => this.handlePlanConfirmation(result, roundId, view),
        error: () => this.reportPlanConfirmationFailure(roundId, view),
      });
  }

  private handlePlanConfirmation(
    result: PlanningResult,
    roundId: number,
    view: symbol | null,
  ): void {
    if (this.skipStaleWrite(roundId, view)) return;
    this.lastResult.set(result);
    this.lastResultRoundId = roundId;
    const confirmed = result.counts['confirmed_slots'] ?? 0;
    const warning = result.notification_warning ?? result.calendar_warning;
    this.feedback.notify(
      warning ? 'error' : 'success',
      warning ? 'Plan bestätigt, Zusatzinformationen unvollständig' : 'Plan bestätigt',
      warning ?? `${confirmed} Termine sind verbindlich.`,
    );
    this.refreshPlanning(roundId);
    void this.router.navigateByUrl(`/confirmed-plans/${roundId}`);
  }

  private clearResultForRoundChange(roundId: number): void {
    if (this.lastResultRoundId === null || this.lastResultRoundId === roundId) return;
    this.lastResult.set(null);
    this.lastResultRoundId = null;
  }

  private reportPlanConfirmationFailure(roundId: number, view: symbol | null): void {
    if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
    this.feedback.notify('error', 'Plan nicht bestätigt', 'Bitte erneut versuchen.');
  }

  private resetPlanningProposal(): void {
    this.pendingProposalReload = null;
    this.proposal.set(null);
    this.editorState.set('idle');
    this.editorError.set(null);
    this.editorViolations.set([]);
  }

  private ensurePlanningRound(roundId: number): boolean {
    if (
      !this.loading() &&
      this.activeRoundId === roundId &&
      this.snapshot()?.round.id === roundId &&
      this.roundContext.roundId() === roundId
    ) {
      return true;
    }
    this.feedback.notify(
      'error',
      'Prüfungsrunde wird aktualisiert',
      'Die Daten der ausgewählten Prüfungsrunde werden noch aktualisiert. Bitte warten Sie kurz und versuchen Sie es erneut.',
    );
    return false;
  }

  private refreshPlanning(roundId: number): void {
    const view = this.activeView;
    if (view && this.activeRoundId === roundId) this.loadPlanning(roundId, view);
  }

  private isSelectedRound(roundId: number): boolean {
    return this.roundContext.roundId() === roundId;
  }

  private captureRoundId(): number {
    return this.activeRoundId ?? this.roundContext.roundId();
  }

  private proposalErrorMessage(error: ApplicationError): string {
    if (error.kind === 'forbidden') {
      return 'Sie haben keine Berechtigung, diesen Planungsvorschlag zu bearbeiten.';
    }
    if (error.kind === 'not-found') return 'Der Planungsvorschlag ist nicht mehr verfügbar.';
    if (error.message) return error.message;
    return 'Der Planungsvorschlag konnte nicht geladen werden. Bitte versuchen Sie es erneut.';
  }
}
