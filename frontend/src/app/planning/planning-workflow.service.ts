import { computed, effect, Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { defer, filter, finalize, switchMap } from 'rxjs';

import type {
  AvailabilityRequest,
  CandidateDayGenerationResult,
  CandidateExamDay,
  EditablePlanningProposal,
  ExamRoundUpdate,
  PlanningResult,
  PlanningValidationViolation,
} from '../api/api.models';
import { ApplicationError } from '../application/application-error';
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
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
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
  private readonly workspace = inject(ApplicationWorkspaceService);
  private readonly pending = signal(false);
  private activeView: symbol | null = null;
  private effectVersion = 0;
  private readonly pendingAvailability = new Set<string>();

  readonly actionBusy = computed(() => this.pending() || this.workspace.actionBusy());
  readonly viewEffect = signal<PlanningViewEffect | null>(null);
  readonly lastResult = signal<PlanningResult | null>(null);
  readonly proposal = signal<EditablePlanningProposal | null>(null);
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
    effect(() => {
      const round = this.workspace.round();
      if (round?.status === 'plan_proposed') {
        this.loadPlanningProposal();
      } else {
        this.resetPlanningProposal();
      }
    });
    this.sessionScope.changes$.subscribe(() => this.resetForSessionChange());
  }

  activateView(view: symbol): void {
    this.activeView = view;
    this.viewEffect.set(null);
  }

  deactivateView(view: symbol): void {
    if (this.activeView !== view) return;
    this.activeView = null;
    this.viewEffect.set(null);
  }

  resetForRoundChange(): void {
    this.lastResult.set(null);
    this.candidateDayGeneration.set(null);
    this.resetPlanningProposal();
  }

  private resetForSessionChange(): void {
    this.lastResult.set(null);
    this.candidateDayGeneration.set(null);
    this.resetPlanningProposal();
    this.editorError.set(null);
    this.editorViolations.set([]);
  }

  requestPlanConfirmation(view = this.activeView): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('planning-proposal:confirm')) {
      this.feedback.roleRestriction();
      return;
    }
    if (!this.beginOperation()) return;
    const roundId = this.roundContext.roundId();
    this.sessionScope
      .forCurrentSession(
        this.feedback.confirm$(
          'Terminplan bestätigen?',
          'Der aktuelle Planungsvorschlag wird als verbindlicher Terminplan bestätigt.',
          'Plan verbindlich bestätigen',
        ),
      )
      .pipe(
        filter((confirmed) => confirmed && this.isCurrentView(view)),
        switchMap(() => defer(() => this.planning.confirmPlan())),
        finalize(() => this.pending.set(false)),
      )
      .subscribe({
        next: (result) => this.handlePlanConfirmation(result, roundId, view),
        error: () => this.reportPlanConfirmationFailure(roundId, view),
      });
  }

  savePlanningSettings(payload: PlanningSettingsPayload, view = this.activeView): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('planning-settings:write')) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    if (!this.beginOperation()) return;
    this.sessionScope
      .forCurrentSession(this.planning.savePlanningSettings(payload, roundId))
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: () => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.feedback.notify(
            'success',
            'Planungsrahmen gespeichert',
            'Die Änderungen sind übernommen.',
          );
          this.workspace.refresh();
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

  saveExamRound(payload: ExamRoundUpdate, view = this.activeView): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('round:write')) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    if (!this.beginOperation()) return;
    this.sessionScope
      .forCurrentSession(this.planning.updateExamRound(payload, roundId))
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: () => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.feedback.notify(
            'success',
            'Prüfungsrunde gespeichert',
            'Die Änderungen sind übernommen.',
          );
          this.workspace.refresh();
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

  requestAvailabilities(payload: AvailabilityRequest, view = this.activeView): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('availability:coordinate')) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    if (!this.beginOperation()) return;
    this.sessionScope
      .forCurrentSession(this.planning.requestAvailabilities(payload, roundId))
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: (result) => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.feedback.notify(
            result.notification_warning ? 'error' : 'success',
            result.notification_warning
              ? 'Terminorganisation gestartet, Benachrichtigungen unvollständig'
              : 'Verfügbarkeiten angefragt',
            result.notification_warning ?? 'Die Terminorganisation ist jetzt in Abstimmung.',
          );
          this.workspace.refresh();
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

  createCandidateDay(payload: CandidateExamDayPayload, view = this.activeView): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('candidate-days:create')) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    if (!this.beginOperation()) return;
    this.sessionScope
      .forCurrentSession(this.planning.createCandidateExamDay(payload, roundId))
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: (day) => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.emitViewEffect(view, { type: 'reset-candidate-day-draft' });
          this.feedback.notify('success', 'Prüfungstag angelegt', day.date);
          this.workspace.refresh();
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

  generateCandidateDays(payload: PlanningSettingsPayload, view = this.activeView): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.canGenerateCandidateDays()) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    if (!this.beginOperation()) return;
    this.sessionScope
      .forCurrentSession(
        this.planning
          .savePlanningSettings(payload, roundId)
          .pipe(switchMap(() => this.planning.generateCandidateExamDays(roundId))),
      )
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: (result) => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.candidateDayGeneration.set(result);
          this.feedback.notify(
            'success',
            'Mögliche Prüfungstage berechnet',
            `${result.counts.created} angelegt, ${result.counts.existing} bereits vorhanden.`,
          );
          this.workspace.refresh();
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

  toggleCandidateDay(day: CandidateExamDay, view = this.activeView): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('candidate-days:toggle')) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    const nextActive = day.is_active ? 0 : 1;
    if (!this.beginOperation()) return;
    this.sessionScope
      .forCurrentSession(this.planning.updateCandidateExamDay(day.id, { is_active: nextActive }))
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: () => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.feedback.notify(
            'success',
            `Prüfungstag ${nextActive ? 'aktiviert' : 'deaktiviert'}`,
            day.date,
          );
          this.workspace.refresh();
        },
        error: () => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.feedback.notify('error', 'Prüfungstag nicht geändert', 'Bitte erneut versuchen.');
        },
      });
  }

  saveAvailability(payload: AvailabilityPayload, view = this.activeView): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) {
      this.emitViewEffect(view, { type: 'availability-error', payload, usePersistedValue: true });
      return;
    }
    const roundId = this.roundContext.roundId();
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
    const availabilityKey = `${payload.committee_member_id}:${payload.candidate_exam_day_id}`;
    if (this.pendingAvailability.has(availabilityKey)) return;
    this.pendingAvailability.add(availabilityKey);
    this.sessionScope
      .forCurrentSession(this.planning.saveMemberAvailability(payload, roundId))
      .pipe(finalize(() => this.pendingAvailability.delete(availabilityKey)))
      .subscribe({
        next: (availability) => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.workspace.board.update((board) =>
            board
              ? {
                  ...board,
                  availabilities: [
                    ...board.availabilities.filter(
                      (item) =>
                        item.committee_member_id !== availability.committee_member_id ||
                        item.candidate_exam_day_id !== availability.candidate_exam_day_id,
                    ),
                    availability,
                  ],
                }
              : board,
          );
          this.emitViewEffect(view, {
            type: 'availability-saved',
            payload,
            availability: availability.availability,
          });
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

  generateProposal(view = this.activeView): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('planning-proposal:generate')) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    if (!this.beginOperation()) return;
    this.sessionScope
      .forCurrentSession(this.planning.generateProposal())
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: (result) => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.lastResult.set(result);
          const planned = result.counts['planned_slots'] ?? 0;
          const suffix = result.validation?.passed === false ? ' mit Hinweisen' : '';
          this.feedback.notify(
            'success',
            'Planungsvorschlag erzeugt',
            `${planned} Termine${suffix}`,
          );
          this.workspace.refresh();
        },
        error: () => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
          this.feedback.notify('error', 'Planung nicht erzeugt', 'Bitte Planungsdaten prüfen.');
        },
      });
  }

  confirmPlan(view = this.activeView): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('planning-proposal:confirm')) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    if (!this.beginOperation()) return;
    this.submitPlanConfirmation(roundId, view);
  }

  loadPlanningProposal(view = this.activeView): void {
    if (this.workspace.round()?.status !== 'plan_proposed') return;
    const roundId = this.roundContext.roundId();
    this.editorState.set('loading');
    this.editorError.set(null);
    this.editorViolations.set([]);
    this.sessionScope.forCurrentSession(this.planning.getPlanningProposal()).subscribe({
      next: (proposal) => {
        if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
        this.proposal.set(proposal);
        this.editorState.set('ready');
      },
      error: (error: ApplicationError) => {
        if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
        this.editorState.set('error');
        this.editorError.set(this.proposalErrorMessage(error));
      },
    });
  }

  reloadPlanningProposal(view = this.activeView): void {
    this.loadPlanningProposal(view);
  }

  savePlanningProposal(proposal: EditablePlanningProposal, view = this.activeView): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('planning-proposal:replace')) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    if (!this.beginOperation()) return;
    this.editorState.set('saving');
    this.editorError.set(null);
    this.editorViolations.set([]);
    this.sessionScope
      .forCurrentSession(this.planning.savePlanningProposal(proposal))
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: (saved) => {
          if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) {
            if (this.isSelectedRound(roundId)) this.workspace.refresh();
            return;
          }
          this.proposal.set(saved);
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
    if (this.pending() || this.workspace.actionBusy()) return false;
    this.pending.set(true);
    return true;
  }

  private isCurrentView(view: symbol | null): boolean {
    return view === null || view === this.activeView;
  }

  private emitViewEffect(view: symbol | null, effect: PlanningViewEffectCommand): void {
    if (!this.isCurrentView(view)) return;
    this.viewEffect.set({ ...effect, version: ++this.effectVersion });
  }

  private submitPlanConfirmation(roundId: number, view: symbol | null): void {
    this.sessionScope
      .forCurrentSession(defer(() => this.planning.confirmPlan()))
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
    if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
    this.lastResult.set(result);
    const confirmed = result.counts['confirmed_slots'] ?? 0;
    const warning = result.notification_warning ?? result.calendar_warning;
    this.feedback.notify(
      warning ? 'error' : 'success',
      warning ? 'Plan bestätigt, Zusatzinformationen unvollständig' : 'Plan bestätigt',
      warning ?? `${confirmed} Termine sind verbindlich.`,
    );
    this.workspace.refresh();
    void this.router.navigateByUrl(`/confirmed-plans/${roundId}`);
  }

  private reportPlanConfirmationFailure(roundId: number, view: symbol | null): void {
    if (!this.isSelectedRound(roundId) || !this.isCurrentView(view)) return;
    this.feedback.notify('error', 'Plan nicht bestätigt', 'Bitte erneut versuchen.');
  }

  private resetPlanningProposal(): void {
    this.proposal.set(null);
    this.editorState.set('idle');
    this.editorError.set(null);
    this.editorViolations.set([]);
  }

  private ensureWorkspaceMatchesSelectedRound(): boolean {
    if (!this.workspace.loading() && this.workspace.round()?.id === this.roundContext.roundId()) {
      return true;
    }
    this.feedback.notify(
      'error',
      'Prüfungsrunde wird aktualisiert',
      'Die Daten der ausgewählten Prüfungsrunde werden noch aktualisiert. Bitte warten Sie kurz und versuchen Sie es erneut.',
    );
    return false;
  }

  private isSelectedRound(roundId: number): boolean {
    return this.roundContext.roundId() === roundId;
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
