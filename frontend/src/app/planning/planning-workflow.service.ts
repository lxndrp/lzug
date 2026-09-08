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
import { PlanningApiService } from '../api/planning-api.service';
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

/** Planning commands and editor state for the selected examination round. */
@Injectable({ providedIn: 'root' })
export class PlanningWorkflowService {
  private readonly api = inject(PlanningApiService);
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
    if (!this.auth.hasCapability('planning-settings:write')) {
      this.feedback.roleRestriction();
      return;
    }
    this.workspace.actionBusy.set(true);
    this.api
      .savePlanningSettings(payload)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.feedback.notify(
            'success',
            'Planungsrahmen gespeichert',
            'Die Änderungen sind übernommen.',
          );
          this.workspace.refresh();
        },
        error: () =>
          this.feedback.notify(
            'error',
            'Planungsrahmen nicht gespeichert',
            'Bitte erneut versuchen.',
          ),
      });
  }

  saveExamRound(payload: ExamRoundUpdate): void {
    if (!this.auth.hasCapability('round:write')) {
      this.feedback.roleRestriction();
      return;
    }
    this.workspace.actionBusy.set(true);
    this.api
      .updateExamRound(payload)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.feedback.notify(
            'success',
            'Prüfungsrunde gespeichert',
            'Die Änderungen sind übernommen.',
          );
          this.workspace.refresh();
        },
        error: () =>
          this.feedback.notify(
            'error',
            'Prüfungsrunde nicht gespeichert',
            'Bitte Eingaben prüfen.',
          ),
      });
  }

  requestAvailabilities(payload: AvailabilityRequest): void {
    if (!this.auth.hasCapability('availability:coordinate')) {
      this.feedback.roleRestriction();
      return;
    }
    this.workspace.actionBusy.set(true);
    this.api
      .requestAvailabilities(payload)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (result) => {
          this.feedback.notify(
            result.notification_warning ? 'error' : 'success',
            result.notification_warning
              ? 'Terminorganisation gestartet, Benachrichtigungen unvollständig'
              : 'Verfügbarkeiten angefragt',
            result.notification_warning ?? 'Die Terminorganisation ist jetzt in Abstimmung.',
          );
          this.workspace.refresh();
        },
        error: () =>
          this.feedback.notify(
            'error',
            'Verfügbarkeiten nicht angefragt',
            'Gespeicherte Angaben bleiben erhalten. Bitte Voraussetzungen prüfen.',
          ),
      });
  }

  createCandidateDay(payload: CandidateExamDayPayload): void {
    if (!this.auth.hasCapability('candidate-days:create')) {
      this.feedback.roleRestriction();
      return;
    }
    this.workspace.actionBusy.set(true);
    this.api
      .createCandidateExamDay(payload)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (day) => {
          this.planningComponent?.resetCandidateDayDraft();
          this.feedback.notify('success', 'Prüfungstag angelegt', day.date);
          this.workspace.refresh();
        },
        error: () =>
          this.feedback.notify(
            'error',
            'Prüfungstag nicht angelegt',
            'Die Eingabe bleibt erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  generateCandidateDays(payload: PlanningSettingsPayload): void {
    if (!this.canGenerateCandidateDays()) {
      this.feedback.roleRestriction();
      return;
    }
    this.workspace.actionBusy.set(true);
    this.api
      .savePlanningSettings(payload)
      .pipe(
        switchMap(() => this.api.generateCandidateExamDays()),
        finalize(() => this.workspace.actionBusy.set(false)),
      )
      .subscribe({
        next: (result) => {
          this.candidateDayGeneration.set(result);
          this.feedback.notify(
            'success',
            'Mögliche Prüfungstage berechnet',
            `${result.counts.created} angelegt, ${result.counts.existing} bereits vorhanden.`,
          );
          this.workspace.refresh();
        },
        error: () =>
          this.feedback.notify(
            'error',
            'Prüfungstage nicht berechnet',
            'Planungszeitraum und Bundesland konnten nicht verarbeitet werden.',
          ),
      });
  }

  toggleCandidateDay(day: CandidateExamDay): void {
    if (!this.auth.hasCapability('candidate-days:toggle')) {
      this.feedback.roleRestriction();
      return;
    }
    const nextActive = day.is_active ? 0 : 1;
    this.workspace.actionBusy.set(true);
    this.api
      .updateCandidateExamDay(day.id, { is_active: nextActive })
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.feedback.notify(
            'success',
            `Prüfungstag ${nextActive ? 'aktiviert' : 'deaktiviert'}`,
            day.date,
          );
          this.workspace.refresh();
        },
        error: () =>
          this.feedback.notify('error', 'Prüfungstag nicht geändert', 'Bitte erneut versuchen.'),
      });
  }

  saveAvailability(payload: AvailabilityPayload): void {
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
    this.api.saveMemberAvailability(payload).subscribe({
      next: (availability) => {
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
    if (!this.auth.hasCapability('planning-proposal:generate')) {
      this.feedback.roleRestriction();
      return;
    }
    this.workspace.actionBusy.set(true);
    this.api
      .generateProposal()
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (result) => {
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
        error: () =>
          this.feedback.notify('error', 'Planung nicht erzeugt', 'Bitte Planungsdaten prüfen.'),
      });
  }

  confirmPlan(): void {
    if (!this.auth.hasCapability('planning-proposal:confirm')) {
      this.feedback.roleRestriction();
      return;
    }
    this.workspace.actionBusy.set(true);
    this.api
      .confirmPlan()
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (result) => {
          this.lastResult.set(result);
          const confirmed = result.counts['confirmed_slots'] ?? 0;
          const warning = result.notification_warning ?? result.calendar_warning;
          this.feedback.notify(
            warning ? 'error' : 'success',
            warning ? 'Plan bestätigt, Zusatzinformationen unvollständig' : 'Plan bestätigt',
            warning ?? `${confirmed} Termine sind verbindlich.`,
          );
          this.workspace.refresh();
          void this.router.navigateByUrl(`/confirmed-plans/${this.roundContext.roundId()}`);
        },
        error: () =>
          this.feedback.notify('error', 'Plan nicht bestätigt', 'Bitte erneut versuchen.'),
      });
  }

  loadPlanningProposal(): void {
    if (this.workspace.round()?.status !== 'plan_proposed') return;
    this.editorState.set('loading');
    this.editorError.set(null);
    this.editorViolations.set([]);
    this.api.getPlanningProposal().subscribe({
      next: (proposal) => {
        this.proposal.set(proposal);
        this.editorState.set('ready');
      },
      error: (error: { status?: number; error?: { error?: { message?: string } | string } }) => {
        this.editorState.set('error');
        this.editorError.set(this.proposalErrorMessage(error));
      },
    });
  }

  reloadPlanningProposal(): void {
    this.loadPlanningProposal();
  }

  savePlanningProposal(proposal: EditablePlanningProposal): void {
    if (!this.auth.hasCapability('planning-proposal:replace')) {
      this.feedback.roleRestriction();
      return;
    }
    this.editorState.set('saving');
    this.editorError.set(null);
    this.editorViolations.set([]);
    this.api.savePlanningProposal(proposal).subscribe({
      next: (saved) => {
        this.proposal.set(saved);
        this.editorState.set('ready');
        this.feedback.notify(
          'success',
          'Änderungen gespeichert',
          'Der Planungsvorschlag ist aktualisiert.',
        );
      },
      error: (error: {
        status?: number;
        error?: {
          error?:
            | {
                code?: string;
                message?: string;
                violations?: PlanningValidationViolation[];
              }
            | string;
        };
      }) => {
        this.editorState.set('error');
        const detail = typeof error.error?.error === 'object' ? error.error.error : undefined;
        this.editorViolations.set(detail?.violations ?? []);
        this.editorError.set(
          error.status === 409
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

  private proposalErrorMessage(error: {
    status?: number;
    error?: { error?: { message?: string } | string };
  }): string {
    if (error.status === 403) {
      return 'Sie haben keine Berechtigung, diesen Planungsvorschlag zu bearbeiten.';
    }
    if (error.status === 404) return 'Der Planungsvorschlag ist nicht mehr verfügbar.';
    if (typeof error.error?.error === 'object' && error.error.error.message) {
      return error.error.error.message;
    }
    if (typeof error.error?.error === 'string') return error.error.error;
    return 'Der Planungsvorschlag konnte nicht geladen werden. Bitte versuchen Sie es erneut.';
  }
}
