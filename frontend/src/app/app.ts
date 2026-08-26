import {
  Component,
  DestroyRef,
  ElementRef,
  HostListener,
  Injector,
  ViewChild,
  afterNextRender,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { TuiButton, TuiNotification, TuiRoot } from '@taiga-ui/core';
import { TuiConfirmService } from '@taiga-ui/kit';
import { filter, finalize, switchMap } from 'rxjs';

import {
  AvailabilityRequest,
  CandidateDayGenerationResult,
  CandidateExamDay,
  CommitteeMember,
  EditablePlanningProposal,
  ExamRound,
  ExamRoundUpdate,
  Location,
  MasterData,
  PlanningBoard,
  PlanningResult,
  PlanningValidationViolation,
  RoundSummary,
} from './api/api.models';
import { PlanningApiService } from './api/planning-api.service';
import { RoundContextService } from './api/round-context.service';
import { AppView } from './app-view';
import { appIcons } from './app-icons';
import { AppIconDirective } from './app-icon.directive';
import { ExamHalfYearsComponent } from './exam-half-years/exam-half-years.component';
import {
  CandidatePayload,
  CandidatesComponent,
  CandidateUpdate,
} from './candidates/candidates.component';
import {
  CommitteeComponent,
  CommitteeMemberPayload,
  CommitteePayload,
} from './committee/committee.component';
import { DashboardComponent } from './dashboard/dashboard.component';
import {
  LocationPayload,
  LocationsComponent,
  LocationUpdate,
} from './locations/locations.component';
import {
  AvailabilityPayload,
  CandidateExamDayPayload,
  PlanningComponent,
  PlanningSettingsPayload,
} from './planning/planning.component';
import { ProposalEditorState } from './planning/planning-proposal-editor.component';
import {
  SchedulingOverviewAction,
  SchedulingOverviewComponent,
} from './scheduling-overview/scheduling-overview.component';
import { ConfirmedPlansComponent } from './confirmed-plans/confirmed-plans.component';
import { ExamDayComponent } from './exam-day/exam-day.component';
import { AuthFlowComponent } from './auth/auth-flow.component';
import { AuthService } from './auth/auth.service';
import { RuntimeNoticeComponent } from './runtime/runtime-notice.component';
import { NotificationsComponent } from './notifications/notifications.component';

@Component({
  selector: 'app-root',
  imports: [
    AppIconDirective,
    AuthFlowComponent,
    CandidatesComponent,
    CommitteeComponent,
    ConfirmedPlansComponent,
    ExamDayComponent,
    DashboardComponent,
    ExamHalfYearsComponent,
    LocationsComponent,
    NotificationsComponent,
    PlanningComponent,
    RuntimeNoticeComponent,
    SchedulingOverviewComponent,
    TuiButton,
    TuiNotification,
    TuiRoot,
  ],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(PlanningApiService);
  private readonly roundContext = inject(RoundContextService);
  private readonly confirm = inject(TuiConfirmService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly injector = inject(Injector);
  private readonly router = inject(Router);
  @ViewChild('sidebarClose') private sidebarClose?: ElementRef<HTMLButtonElement>;
  @ViewChild('sidebarToggle') private sidebarToggle?: ElementRef<HTMLButtonElement>;
  @ViewChild(CandidatesComponent) private candidatesComponent?: CandidatesComponent;
  @ViewChild(CommitteeComponent) private committeeComponent?: CommitteeComponent;
  @ViewChild(LocationsComponent) private locationsComponent?: LocationsComponent;
  @ViewChild(PlanningComponent) private planningComponent?: PlanningComponent;

  protected readonly icons = appIcons;
  protected readonly round = signal<ExamRound | null>(null);
  protected readonly summary = signal<RoundSummary | null>(null);
  protected readonly board = signal<PlanningBoard | null>(null);
  protected readonly masterData = signal<MasterData | null>(null);
  protected readonly lastPlanningResult = signal<PlanningResult | null>(null);
  protected readonly planningProposal = signal<EditablePlanningProposal | null>(null);
  protected readonly proposalEditorState = signal<ProposalEditorState>('idle');
  protected readonly proposalEditorError = signal<string | null>(null);
  protected readonly proposalEditorViolations = signal<PlanningValidationViolation[]>([]);
  protected readonly candidateDayGenerationResult = signal<CandidateDayGenerationResult | null>(
    null,
  );
  protected readonly activeView = signal<AppView>('dashboard');
  protected readonly sidebarVisible = signal(
    typeof window === 'undefined' || window.innerWidth >= 768,
  );
  protected readonly selectedCommitteeId = signal<number | null>(null);
  protected readonly message = signal('Bereit');
  protected readonly loading = signal(false);
  protected readonly actionBusy = signal(false);
  protected readonly contextualRoundId = signal<number | null>(null);
  protected readonly contextualDayId = signal<number | null>(null);
  protected readonly applicationVersion = signal<string | null>(null);
  protected readonly feedback = signal<{
    type: 'success' | 'error';
    title: string;
    message: string;
  } | null>(null);
  protected readonly roleSwitchBusy = signal(false);
  protected readonly demoSession = computed(() => {
    const session = this.auth.session();
    return session?.demo_role ? session : null;
  });
  protected readonly isDemoExaminer = computed(() => this.demoSession()?.demo_role === 'examiner');
  protected readonly canCoordinatePlanning = computed(
    () =>
      this.hasCapability('planning-settings:write') ||
      this.hasCapability('availability:coordinate'),
  );
  protected readonly canCoordinateAttendance = computed(
    () => this.hasCapability('attendance:coordinate') || this.hasCapability('exam-status:write'),
  );
  protected readonly directAccessDenied = computed(
    () => this.demoSession() !== null && !this.canAccessView(this.activeView()),
  );

  protected readonly pageTitle = computed(() => {
    const labels: Record<AppView, string> = {
      dashboard: 'Übersicht',
      'scheduling-overview': 'Terminorganisationen',
      'confirmed-plans': 'Prüfungspläne',
      'exam-day': 'Prüfungstag',
      candidates: 'Prüflinge',
      committee: 'Prüfungsausschüsse',
      planning: 'Terminorganisation',
      locations: 'Prüfungsorte',
      'exam-half-years': 'Prüfungshalbjahre',
      notifications: 'Benachrichtigungen',
    };
    return labels[this.activeView()];
  });

  protected readonly activeContext = computed(() => {
    const round = this.round();
    const masterData = this.masterData();
    if (!round || !masterData) return null;

    const halfYear = masterData.examHalfYears.find((item) => item.id === round.exam_half_year_id);
    const committee = masterData.committees.find((item) => item.id === round.committee_id);
    if (!halfYear || !committee) return null;

    return {
      halfYear: `${halfYear.season === 'summer' ? 'Sommer' : 'Winter'} ${halfYear.year}`,
      round: round.name,
      committee: committee.name,
      status: this.roundStatusLabel(round.status),
    };
  });

  protected readonly isContextualView = computed(() =>
    [
      'dashboard',
      'scheduling-overview',
      'confirmed-plans',
      'exam-day',
      'candidates',
      'planning',
    ].includes(this.activeView()),
  );

  protected readonly breadcrumb = computed(() => {
    if (this.activeView() === 'exam-half-years') return 'Prüfungskontext';
    if (this.activeView() === 'notifications') return 'Persönlicher Bereich';
    if (['committee', 'locations'].includes(this.activeView())) return 'Globale Bereiche';
    return 'Aktueller Prüfungskontext';
  });

  constructor() {
    let previousAuthState: ReturnType<AuthService['state']> | undefined;
    effect(() => {
      const authState = this.auth.state();
      if (previousAuthState === 'anonymous' && authState === 'authenticated') {
        this.refresh();
      }
      previousAuthState = authState;
    });
    this.router.events
      .pipe(
        filter((event): event is NavigationEnd => event instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((event) => {
        this.applyRoute(event.urlAfterRedirects, true);
      });
    this.applyRoute(this.router.url, false);
    this.auth.initialize().subscribe((authenticated) => {
      if (authenticated) this.refresh();
    });
  }

  protected refresh(): void {
    if (this.auth.state() !== 'authenticated') return;
    this.loading.set(true);
    this.api
      .refreshDashboard()
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: ({ root, round, summary, board, masterData }) => {
          this.applicationVersion.set(root.version);
          this.round.set(round);
          this.summary.set(summary);
          this.board.set(board);
          this.masterData.set(masterData);
          if (round.status === 'plan_proposed') {
            this.loadPlanningProposal();
          } else {
            this.resetPlanningProposal();
          }
          if (!this.selectedCommitteeId()) {
            this.selectedCommitteeId.set(masterData.committees[0]?.id ?? null);
          }
          if (this.activeView() === 'planning' && round.status === 'plan_confirmed') {
            void this.router.navigateByUrl(`/confirmed-plans/${round.id}`, {
              replaceUrl: true,
            });
          }
          this.message.set('Daten synchronisiert');
        },
        error: (error: { status?: number }) => {
          if (error.status === 401) {
            this.auth.markAnonymous();
            return;
          }
          this.message.set('Synchronisierung nicht möglich');
        },
      });
  }

  protected showView(view: AppView): void {
    if (!this.canAccessView(view)) {
      this.activeView.set(view);
      return;
    }
    void this.router.navigateByUrl(`/${this.pathForView(view)}`);
  }

  protected navigateFromShell(view: AppView, event: Event): void {
    event.preventDefault();
    this.showView(view);
    this.closeSidebarOnMobile();
  }

  protected closeSidebarOnMobile(): void {
    if (this.isMobileViewport()) {
      this.closeSidebar();
    }
  }

  protected toggleSidebar(): void {
    if (this.sidebarVisible()) {
      this.closeSidebar();
    } else {
      this.openSidebar();
    }
  }

  protected openSidebar(): void {
    this.sidebarVisible.set(true);
    afterNextRender(() => this.sidebarClose?.nativeElement.focus(), { injector: this.injector });
  }

  protected closeSidebar(): void {
    if (!this.sidebarVisible()) return;

    this.sidebarToggle?.nativeElement.focus();
    this.sidebarVisible.set(false);
  }

  @HostListener('document:keydown.escape', ['$event'])
  protected closeSidebarWithEscape(event: Event): void {
    if (!this.sidebarVisible() || !this.isMobileViewport()) return;

    event.preventDefault();
    this.closeSidebar();
  }

  private isMobileViewport(): boolean {
    return typeof window !== 'undefined' && window.matchMedia('(max-width: 767.98px)').matches;
  }

  protected selectCommittee(id: number | null): void {
    this.selectedCommitteeId.set(id);
  }

  protected selectExamRound(id: number): void {
    this.roundContext.select(id);
    this.lastPlanningResult.set(null);
    this.candidateDayGenerationResult.set(null);
    this.resetPlanningProposal();
    this.refresh();
    this.showView('dashboard');
  }

  protected openSchedulingRound(action: SchedulingOverviewAction): void {
    this.lastPlanningResult.set(null);
    this.candidateDayGenerationResult.set(null);
    const area = action.target === 'confirmed-plan' ? 'confirmed-plans' : 'scheduling-overview';
    void this.router.navigateByUrl(`/${area}/${action.id}`);
  }

  protected cancelScheduling(): void {
    this.showView('scheduling-overview');
  }

  protected roundStatusLabel(status: string): string {
    const labels: Record<string, string> = {
      draft: 'Offen',
      availability_requested: 'Rückmeldungen angefragt',
      availability_closed: 'Rückmeldungen vollständig',
      plan_proposed: 'Planungsvorschlag liegt vor',
      in_progress: 'In Bearbeitung',
      plan_confirmed: 'Plan bestätigt',
    };
    return labels[status] ?? status;
  }

  protected dismissFeedback(): void {
    this.feedback.set(null);
  }

  protected demoRoleLabel(): string {
    return this.demoSession()?.demo_role === 'chair' ? 'Vorsitz' : 'Prüfperson';
  }

  protected demoRoleTask(): string {
    return this.isDemoExaminer()
      ? 'Eigene Verfügbarkeit und Anwesenheit'
      : 'Planung und Koordination';
  }

  protected hasCapability(capability: string): boolean {
    const capabilities = this.auth.session()?.capabilities;
    return capabilities === undefined || capabilities.includes(capability);
  }

  protected canAccessView(view: AppView): boolean {
    if (!this.demoSession()) return true;
    if (view === 'dashboard' || view === 'notifications') return true;
    if (view === 'exam-half-years') return true;
    if (['scheduling-overview', 'planning'].includes(view)) {
      return (
        this.hasCapability('availability:write-own') ||
        this.hasCapability('availability:coordinate') ||
        this.hasCapability('planning-settings:write')
      );
    }
    if (['confirmed-plans', 'exam-day'].includes(view)) {
      return (
        this.hasCapability('attendance:write-own') ||
        this.hasCapability('attendance:coordinate') ||
        this.hasCapability('exam-status:write')
      );
    }
    return false;
  }

  protected switchDemoRole(): void {
    if (!this.demoSession() || this.roleSwitchBusy()) return;
    this.roleSwitchBusy.set(true);
    this.auth
      .logout()
      .pipe(finalize(() => this.roleSwitchBusy.set(false)))
      .subscribe({
        error: () =>
          this.notify(
            'error',
            'Rollenwechsel nicht möglich',
            'Die Demo-Sitzung konnte nicht beendet werden. Bitte erneut versuchen.',
          ),
      });
  }

  protected requestCandidateDeletion(id: number, label: string): void {
    this.requestConfirmation(
      `${label} löschen?`,
      `${label} wird dauerhaft aus der Prüfungsverwaltung entfernt.`,
      `${label} löschen`,
      () => this.deleteCandidate(id, label),
    );
  }

  protected requestLocationDeletion(id: number, label: string): void {
    this.requestConfirmation(
      `${label} löschen?`,
      `${label} wird dauerhaft aus der Prüfungsverwaltung entfernt.`,
      `${label} löschen`,
      () => this.deleteLocation(id, label),
    );
  }

  protected requestPlanConfirmation(): void {
    this.requestConfirmation(
      'Terminplan bestätigen?',
      'Der aktuelle Planungsvorschlag wird als verbindlicher Terminplan bestätigt.',
      'Plan verbindlich bestätigen',
      () => this.confirmPlan(),
    );
  }

  private requestConfirmation(
    title: string,
    message: string,
    confirmLabel: string,
    action: () => void,
  ): void {
    this.confirm.markAsDirty();
    this.confirm
      .withConfirm({
        label: title,
        size: 'm',
        data: { content: message, no: 'Abbrechen', yes: confirmLabel, appearance: 'negative' },
      })
      .pipe(finalize(() => this.confirm.markAsPristine()))
      .subscribe((confirmed) => {
        if (confirmed) {
          action();
        }
      });
  }

  protected createCommittee(payload: CommitteePayload): void {
    this.actionBusy.set(true);
    this.api
      .createCommittee(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (committee) => {
          this.committeeComponent?.resetCommitteeForm();
          this.selectedCommitteeId.set(committee.id);
          this.notify('success', 'Ausschuss angelegt', committee.name);
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Ausschuss nicht gespeichert',
            'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  protected createMember(payload: CommitteeMemberPayload): void {
    this.actionBusy.set(true);
    this.api
      .createMember(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (member) => {
          this.committeeComponent?.resetMemberForm();
          this.selectedCommitteeId.set(member.committee_id);
          this.notify('success', 'Prüfer angelegt', this.fullMemberName(member));
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Prüfer nicht gespeichert',
            'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  protected createCandidate(payload: CandidatePayload): void {
    this.actionBusy.set(true);
    this.api
      .createCandidate(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (candidate) => {
          this.candidatesComponent?.resetDraft();
          this.notify(
            'success',
            'Prüfling angelegt',
            `${candidate.first_name} ${candidate.last_name}`,
          );
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Prüfling nicht gespeichert',
            'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  protected deleteCandidate(id: number, label: string): void {
    this.actionBusy.set(true);
    this.api
      .deleteCandidate(id)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.notify('success', 'Prüfling gelöscht', label);
          this.refresh();
        },
        error: () => this.notify('error', 'Prüfling nicht gelöscht', 'Bitte erneut versuchen.'),
      });
  }

  protected updateCandidate(update: CandidateUpdate): void {
    this.actionBusy.set(true);
    this.api
      .updateCandidate(update.id, update.payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (candidate) => {
          this.candidatesComponent?.finishEditing(candidate.id);
          this.notify(
            'success',
            'Prüfling gespeichert',
            `${candidate.first_name} ${candidate.last_name}`,
          );
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Prüfling nicht gespeichert',
            'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  protected createLocation(payload: LocationPayload): void {
    this.actionBusy.set(true);
    this.api
      .createLocation(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (location) => {
          this.locationsComponent?.resetDraft();
          this.notify('success', 'Prüfungsort angelegt', location.name);
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Prüfungsort nicht gespeichert',
            'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  protected deleteLocation(id: number, label: string): void {
    this.actionBusy.set(true);
    this.api
      .deleteLocation(id)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.notify('success', 'Prüfungsort gelöscht', label);
          this.refresh();
        },
        error: () => this.notify('error', 'Prüfungsort nicht gelöscht', 'Bitte erneut versuchen.'),
      });
  }

  protected updateLocation(update: LocationUpdate): void {
    this.actionBusy.set(true);
    this.api
      .updateLocation(update.id, update.payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (location) => {
          this.locationsComponent?.finishEditing(location.id);
          this.notify('success', 'Prüfungsort gespeichert', `${location.name} · ${location.room}`);
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Prüfungsort nicht gespeichert',
            'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  protected toggleLocation(location: Location): void {
    const nextActive = location.is_active === 0 ? 1 : 0;
    this.actionBusy.set(true);
    this.api
      .updateLocation(location.id, { is_active: nextActive })
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.notify(
            'success',
            `Prüfungsort ${nextActive ? 'aktiviert' : 'deaktiviert'}`,
            location.name,
          );
          this.refresh();
        },
        error: () => this.notify('error', 'Status nicht geändert', 'Bitte erneut versuchen.'),
      });
  }

  protected savePlanningSettings(payload: PlanningSettingsPayload): void {
    if (!this.hasCapability('planning-settings:write')) {
      this.notifyRoleRestriction();
      return;
    }
    this.actionBusy.set(true);
    this.api
      .savePlanningSettings(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.notify('success', 'Planungsrahmen gespeichert', 'Die Änderungen sind übernommen.');
          this.refresh();
        },
        error: () =>
          this.notify('error', 'Planungsrahmen nicht gespeichert', 'Bitte erneut versuchen.'),
      });
  }

  protected saveExamRound(payload: ExamRoundUpdate): void {
    if (!this.hasCapability('round:write')) {
      this.notifyRoleRestriction();
      return;
    }
    this.actionBusy.set(true);
    this.api
      .updateExamRound(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.notify('success', 'Prüfungsrunde gespeichert', 'Die Änderungen sind übernommen.');
          this.refresh();
        },
        error: () =>
          this.notify('error', 'Prüfungsrunde nicht gespeichert', 'Bitte Eingaben prüfen.'),
      });
  }

  protected requestAvailabilities(payload: AvailabilityRequest): void {
    if (!this.hasCapability('availability:coordinate')) {
      this.notifyRoleRestriction();
      return;
    }
    this.actionBusy.set(true);
    this.api
      .requestAvailabilities(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (result) => {
          this.notify(
            result.notification_warning ? 'error' : 'success',
            result.notification_warning
              ? 'Terminorganisation gestartet, Benachrichtigungen unvollständig'
              : 'Verfügbarkeiten angefragt',
            result.notification_warning ?? 'Die Terminorganisation ist jetzt in Abstimmung.',
          );
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Verfügbarkeiten nicht angefragt',
            'Gespeicherte Angaben bleiben erhalten. Bitte Voraussetzungen prüfen.',
          ),
      });
  }

  protected createCandidateDay(payload: CandidateExamDayPayload): void {
    if (!this.hasCapability('candidate-days:generate')) {
      this.notifyRoleRestriction();
      return;
    }
    this.actionBusy.set(true);
    this.api
      .createCandidateExamDay(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (day) => {
          this.planningComponent?.resetCandidateDayDraft();
          this.notify('success', 'Prüfungstag angelegt', day.date);
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Prüfungstag nicht angelegt',
            'Die Eingabe bleibt erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  protected generateCandidateDays(payload: PlanningSettingsPayload): void {
    if (!this.hasCapability('candidate-days:generate')) {
      this.notifyRoleRestriction();
      return;
    }
    this.actionBusy.set(true);
    this.api
      .savePlanningSettings(payload)
      .pipe(
        switchMap(() => this.api.generateCandidateExamDays()),
        finalize(() => this.actionBusy.set(false)),
      )
      .subscribe({
        next: (result) => {
          this.candidateDayGenerationResult.set(result);
          this.notify(
            'success',
            'Mögliche Prüfungstage berechnet',
            `${result.counts.created} angelegt, ${result.counts.existing} bereits vorhanden.`,
          );
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Prüfungstage nicht berechnet',
            'Planungszeitraum und Bundesland konnten nicht verarbeitet werden.',
          ),
      });
  }

  protected toggleCandidateDay(day: CandidateExamDay): void {
    if (!this.hasCapability('candidate-days:generate')) {
      this.notifyRoleRestriction();
      return;
    }
    const nextActive = day.is_active ? 0 : 1;
    this.actionBusy.set(true);
    this.api
      .updateCandidateExamDay(day.id, { is_active: nextActive })
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.notify(
            'success',
            `Prüfungstag ${nextActive ? 'aktiviert' : 'deaktiviert'}`,
            day.date,
          );
          this.refresh();
        },
        error: () => this.notify('error', 'Prüfungstag nicht geändert', 'Bitte erneut versuchen.'),
      });
  }

  protected saveAvailability(payload: AvailabilityPayload): void {
    const session = this.demoSession();
    const canSave =
      this.hasCapability('availability:coordinate') || this.hasCapability('availability:write-own');
    if (
      !canSave ||
      (session?.demo_role === 'examiner' &&
        payload.committee_member_id !== session.committee_member_id)
    ) {
      this.notifyRoleRestriction();
      this.planningComponent?.markAvailabilityError(payload);
      return;
    }
    this.api.saveMemberAvailability(payload).subscribe({
      next: (availability) => {
        this.board.update((board) =>
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
        this.notify(
          'error',
          'Verfügbarkeit nicht gespeichert',
          'Die Auswahl wurde zurückgesetzt. Bitte erneut versuchen.',
        );
      },
    });
  }

  protected toggleMember(member: CommitteeMember): void {
    const nextActive = member.is_active ? 0 : 1;
    this.actionBusy.set(true);
    this.api
      .updateMember(member.id, { is_active: nextActive })
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.notify(
            'success',
            `Prüfer ${nextActive ? 'aktiviert' : 'deaktiviert'}`,
            this.fullMemberName(member),
          );
          this.refresh();
        },
        error: () => this.notify('error', 'Status nicht geändert', 'Bitte erneut versuchen.'),
      });
  }

  protected generateProposal(): void {
    if (!this.hasCapability('planning-proposal:generate')) {
      this.notifyRoleRestriction();
      return;
    }
    this.actionBusy.set(true);
    this.api
      .generateProposal()
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (result) => {
          this.lastPlanningResult.set(result);
          const planned = result.counts['planned_slots'] ?? 0;
          const suffix = result.validation?.passed === false ? ' mit Hinweisen' : '';
          this.notify('success', 'Planungsvorschlag erzeugt', `${planned} Termine${suffix}`);
          this.refresh();
        },
        error: () => this.notify('error', 'Planung nicht erzeugt', 'Bitte Planungsdaten prüfen.'),
      });
  }

  protected confirmPlan(): void {
    if (!this.hasCapability('planning-proposal:confirm')) {
      this.notifyRoleRestriction();
      return;
    }
    this.actionBusy.set(true);
    this.api
      .confirmPlan()
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (result) => {
          this.lastPlanningResult.set(result);
          const confirmed = result.counts['confirmed_slots'] ?? 0;
          this.notify(
            result.notification_warning ? 'error' : 'success',
            result.notification_warning
              ? 'Plan bestätigt, Benachrichtigungen unvollständig'
              : 'Plan bestätigt',
            result.notification_warning ?? `${confirmed} Termine sind verbindlich.`,
          );
          this.refresh();
          void this.router.navigateByUrl(`/confirmed-plans/${this.roundContext.roundId()}`);
        },
        error: () => this.notify('error', 'Plan nicht bestätigt', 'Bitte erneut versuchen.'),
      });
  }

  protected loadPlanningProposal(): void {
    if (this.round()?.status !== 'plan_proposed') return;
    this.proposalEditorState.set('loading');
    this.proposalEditorError.set(null);
    this.proposalEditorViolations.set([]);
    this.api.getPlanningProposal().subscribe({
      next: (proposal) => {
        this.planningProposal.set(proposal);
        this.proposalEditorState.set('ready');
      },
      error: (error: { status?: number; error?: { error?: { message?: string } | string } }) => {
        this.proposalEditorState.set('error');
        this.proposalEditorError.set(this.proposalErrorMessage(error));
      },
    });
  }

  protected reloadPlanningProposal(): void {
    this.loadPlanningProposal();
  }

  protected savePlanningProposal(proposal: EditablePlanningProposal): void {
    this.proposalEditorState.set('saving');
    this.proposalEditorError.set(null);
    this.proposalEditorViolations.set([]);
    this.api.savePlanningProposal(proposal).subscribe({
      next: (saved) => {
        this.planningProposal.set(saved);
        this.proposalEditorState.set('ready');
        this.notify('success', 'Änderungen gespeichert', 'Der Planungsvorschlag ist aktualisiert.');
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
        this.proposalEditorState.set('error');
        const detail = typeof error.error?.error === 'object' ? error.error.error : undefined;
        this.proposalEditorViolations.set(detail?.violations ?? []);
        this.proposalEditorError.set(
          error.status === 409
            ? 'Der Vorschlag wurde zwischenzeitlich geändert. Laden Sie die aktuelle Fassung, bevor Sie erneut speichern.'
            : this.proposalErrorMessage(error),
        );
      },
    });
  }

  private resetPlanningProposal(): void {
    this.planningProposal.set(null);
    this.proposalEditorState.set('idle');
    this.proposalEditorError.set(null);
    this.proposalEditorViolations.set([]);
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

  private notify(type: 'success' | 'error', title: string, message: string): void {
    this.feedback.set({ type, title, message });
  }

  private notifyRoleRestriction(): void {
    this.notify(
      'error',
      'Aktion für diese Rolle nicht verfügbar',
      'Bitte öffnen Sie den für Ihre Demo-Rolle vorgesehenen Aufgabenpfad.',
    );
  }

  private pathForView(view: AppView): string {
    const paths: Record<AppView, string> = {
      dashboard: 'dashboard',
      'scheduling-overview': 'scheduling-overview',
      'confirmed-plans': 'confirmed-plans',
      'exam-day': 'confirmed-plans',
      candidates: 'candidates',
      committee: 'committee',
      planning: 'planning',
      locations: 'locations',
      'exam-half-years': 'exam-half-years',
      notifications: 'notifications',
    };
    return view === 'planning' ? `scheduling-overview/${this.roundContext.roundId()}` : paths[view];
  }

  private viewFromUrl(url: string): AppView {
    const segments = this.urlSegments(url);
    if (segments[0] === 'confirmed-plans' && segments[2] === 'days' && segments[3]) {
      return 'exam-day';
    }
    if (segments[0] === 'scheduling-overview' && segments[1]) {
      return 'planning';
    }
    const segment = segments[0];
    const views: Record<string, AppView> = {
      dashboard: 'dashboard',
      'scheduling-overview': 'scheduling-overview',
      'confirmed-plans': 'confirmed-plans',
      candidates: 'candidates',
      committee: 'committee',
      planning: 'planning',
      locations: 'locations',
      'exam-half-years': 'exam-half-years',
      notifications: 'notifications',
    };
    return views[segment ?? 'dashboard'] ?? 'dashboard';
  }

  private applyRoute(url: string, refreshWhenRoundChanges: boolean): void {
    this.activeView.set(this.viewFromUrl(url));
    const roundId = this.roundIdFromUrl(url);
    this.contextualRoundId.set(roundId);
    this.contextualDayId.set(this.dayIdFromUrl(url));
    if (roundId === null || roundId === this.roundContext.roundId()) {
      return;
    }

    this.roundContext.select(roundId);
    this.lastPlanningResult.set(null);
    this.candidateDayGenerationResult.set(null);
    if (refreshWhenRoundChanges) {
      this.refresh();
    }
  }

  private roundIdFromUrl(url: string): number | null {
    const segments = this.urlSegments(url);
    if (!['scheduling-overview', 'confirmed-plans'].includes(segments[0] ?? '')) {
      return null;
    }
    const id = Number(segments[1]);
    return Number.isInteger(id) && id > 0 ? id : null;
  }

  private dayIdFromUrl(url: string): number | null {
    const segments = this.urlSegments(url);
    if (segments[0] !== 'confirmed-plans' || segments[2] !== 'days') return null;
    const id = Number(segments[3]);
    return Number.isInteger(id) && id > 0 ? id : null;
  }

  private urlSegments(url: string): string[] {
    return url.split('?')[0].split('#')[0].split('/').filter(Boolean);
  }

  private fullMemberName(member: CommitteeMember): string {
    return `${member.first_name} ${member.last_name}`;
  }
}
