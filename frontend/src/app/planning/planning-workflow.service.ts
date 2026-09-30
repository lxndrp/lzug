import { computed, effect, Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { finalize, switchMap } from 'rxjs';

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
import type {
  AvailabilityPayload,
  CandidateExamDayPayload,
  PlanningComponent,
  PlanningSettingsPayload,
} from './planning.component';
import type { ProposalEditorState } from './planning-proposal-editor.component';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { UiFeedbackService } from '../shell/ui-feedback.service';
import { PLANNING_PORT } from './planning.port';

/** Planning commands and editor state for the selected examination round. */
@Injectable({ providedIn: 'root' })
export class PlanningWorkflowService {
  private readonly planning = inject(PLANNING_PORT);
  private readonly auth = inject(AuthService);
  private readonly feedback = inject(UiFeedbackService);
  private readonly roundContext = inject(RoundContextService);
  private readonly router = inject(Router);
  private readonly workspace = inject(ApplicationWorkspaceService);
  private planningComponent?: PlanningComponent;

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
  }

  connect(component?: PlanningComponent): void {
    this.planningComponent = component;
  }

  resetForRoundChange(): void {
    this.lastResult.set(null);
    this.candidateDayGeneration.set(null);
    this.resetPlanningProposal();
  }

  requestPlanConfirmation(): void {
    this.feedback.confirm(
      'Terminplan bestätigen?',
      'Der aktuelle Planungsvorschlag wird als verbindlicher Terminplan bestätigt.',
      'Plan verbindlich bestätigen',
      () => this.confirmPlan(),
    );
  }

  savePlanningSettings(payload: PlanningSettingsPayload): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('planning-settings:write')) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    this.workspace.actionBusy.set(true);
    this.planning
      .savePlanningSettings(payload, roundId)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: () => {
          if (!this.isSelectedRound(roundId)) return;
          this.feedback.notify(
            'success',
            'Planungsrahmen gespeichert',
            'Die Änderungen sind übernommen.',
          );
          this.workspace.refresh();
        },
        error: () => {
          if (!this.isSelectedRound(roundId)) return;
          this.feedback.notify(
            'error',
            'Planungsrahmen nicht gespeichert',
            'Bitte erneut versuchen.',
          );
        },
      });
  }

  saveExamRound(payload: ExamRoundUpdate): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('round:write')) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    this.workspace.actionBusy.set(true);
    this.planning
      .updateExamRound(payload, roundId)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: () => {
          if (!this.isSelectedRound(roundId)) return;
          this.feedback.notify(
            'success',
            'Prüfungsrunde gespeichert',
            'Die Änderungen sind übernommen.',
          );
          this.workspace.refresh();
        },
        error: () => {
          if (!this.isSelectedRound(roundId)) return;
          this.feedback.notify(
            'error',
            'Prüfungsrunde nicht gespeichert',
            'Bitte Eingaben prüfen.',
          );
        },
      });
  }

  requestAvailabilities(payload: AvailabilityRequest): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('availability:coordinate')) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    this.workspace.actionBusy.set(true);
    this.planning
      .requestAvailabilities(payload, roundId)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (result) => {
          if (!this.isSelectedRound(roundId)) return;
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
          if (!this.isSelectedRound(roundId)) return;
          this.feedback.notify(
            'error',
            'Verfügbarkeiten nicht angefragt',
            'Gespeicherte Angaben bleiben erhalten. Bitte Voraussetzungen prüfen.',
          );
        },
      });
  }

  createCandidateDay(payload: CandidateExamDayPayload): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('candidate-days:create')) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    this.workspace.actionBusy.set(true);
    this.planning
      .createCandidateExamDay(payload, roundId)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (day) => {
          if (!this.isSelectedRound(roundId)) return;
          this.planningComponent?.resetCandidateDayDraft();
          this.feedback.notify('success', 'Prüfungstag angelegt', day.date);
          this.workspace.refresh();
        },
        error: () => {
          if (!this.isSelectedRound(roundId)) return;
          this.feedback.notify(
            'error',
            'Prüfungstag nicht angelegt',
            'Die Eingabe bleibt erhalten. Bitte erneut versuchen.',
          );
        },
      });
  }

  generateCandidateDays(payload: PlanningSettingsPayload): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.canGenerateCandidateDays()) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    this.workspace.actionBusy.set(true);
    this.planning
      .savePlanningSettings(payload, roundId)
      .pipe(
        switchMap(() => this.planning.generateCandidateExamDays(roundId)),
        finalize(() => this.workspace.actionBusy.set(false)),
      )
      .subscribe({
        next: (result) => {
          if (!this.isSelectedRound(roundId)) return;
          this.candidateDayGeneration.set(result);
          this.feedback.notify(
            'success',
            'Mögliche Prüfungstage berechnet',
            `${result.counts.created} angelegt, ${result.counts.existing} bereits vorhanden.`,
          );
          this.workspace.refresh();
        },
        error: () => {
          if (!this.isSelectedRound(roundId)) return;
          this.feedback.notify(
            'error',
            'Prüfungstage nicht berechnet',
            'Planungszeitraum und Bundesland konnten nicht verarbeitet werden.',
          );
        },
      });
  }

  toggleCandidateDay(day: CandidateExamDay): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('candidate-days:toggle')) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    const nextActive = day.is_active ? 0 : 1;
    this.workspace.actionBusy.set(true);
    this.planning
      .updateCandidateExamDay(day.id, { is_active: nextActive })
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: () => {
          if (!this.isSelectedRound(roundId)) return;
          this.feedback.notify(
            'success',
            `Prüfungstag ${nextActive ? 'aktiviert' : 'deaktiviert'}`,
            day.date,
          );
          this.workspace.refresh();
        },
        error: () => {
          if (!this.isSelectedRound(roundId)) return;
          this.feedback.notify('error', 'Prüfungstag nicht geändert', 'Bitte erneut versuchen.');
        },
      });
  }

  saveAvailability(payload: AvailabilityPayload): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) {
      this.planningComponent?.markAvailabilityError(payload, true);
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
      this.planningComponent?.markAvailabilityError(payload);
      return;
    }
    this.planning.saveMemberAvailability(payload, roundId).subscribe({
      next: (availability) => {
        if (!this.isSelectedRound(roundId)) return;
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
        this.planningComponent?.markAvailabilitySaved(payload);
      },
      error: () => {
        if (!this.isSelectedRound(roundId)) return;
        this.planningComponent?.markAvailabilityError(payload);
        this.feedback.notify(
          'error',
          'Verfügbarkeit nicht gespeichert',
          'Die Auswahl wurde zurückgesetzt. Bitte erneut versuchen.',
        );
      },
    });
  }

  generateProposal(): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('planning-proposal:generate')) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    this.workspace.actionBusy.set(true);
    this.planning
      .generateProposal()
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (result) => {
          if (!this.isSelectedRound(roundId)) return;
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
          if (!this.isSelectedRound(roundId)) return;
          this.feedback.notify('error', 'Planung nicht erzeugt', 'Bitte Planungsdaten prüfen.');
        },
      });
  }

  confirmPlan(): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('planning-proposal:confirm')) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    this.workspace.actionBusy.set(true);
    this.planning
      .confirmPlan()
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (result) => {
          if (!this.isSelectedRound(roundId)) return;
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
        },
        error: () => {
          if (!this.isSelectedRound(roundId)) return;
          this.feedback.notify('error', 'Plan nicht bestätigt', 'Bitte erneut versuchen.');
        },
      });
  }

  loadPlanningProposal(): void {
    if (this.workspace.round()?.status !== 'plan_proposed') return;
    const roundId = this.roundContext.roundId();
    this.editorState.set('loading');
    this.editorError.set(null);
    this.editorViolations.set([]);
    this.planning.getPlanningProposal().subscribe({
      next: (proposal) => {
        if (!this.isSelectedRound(roundId)) return;
        this.proposal.set(proposal);
        this.editorState.set('ready');
      },
      error: (error: ApplicationError) => {
        if (!this.isSelectedRound(roundId)) return;
        this.editorState.set('error');
        this.editorError.set(this.proposalErrorMessage(error));
      },
    });
  }

  reloadPlanningProposal(): void {
    this.loadPlanningProposal();
  }

  savePlanningProposal(proposal: EditablePlanningProposal): void {
    if (!this.ensureWorkspaceMatchesSelectedRound()) return;
    if (!this.auth.hasCapability('planning-proposal:replace')) {
      this.feedback.roleRestriction();
      return;
    }
    const roundId = this.roundContext.roundId();
    this.editorState.set('saving');
    this.editorError.set(null);
    this.editorViolations.set([]);
    this.planning.savePlanningProposal(proposal).subscribe({
      next: (saved) => {
        if (!this.isSelectedRound(roundId)) return;
        this.proposal.set(saved);
        this.editorState.set('ready');
        this.feedback.notify(
          'success',
          'Änderungen gespeichert',
          'Der Planungsvorschlag ist aktualisiert.',
        );
      },
      error: (error: ApplicationError) => {
        if (!this.isSelectedRound(roundId)) return;
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
