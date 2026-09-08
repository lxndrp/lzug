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
import { filter } from 'rxjs';

import {
  AvailabilityRequest,
  CandidateExamDay,
  CommitteeMember,
  EditablePlanningProposal,
  ExamRoundUpdate,
  ExamRoom,
  ExamVenue,
  ExamVenueContact,
} from './api/api.models';
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
import { CommitteeComponent, CommitteeMemberPayload } from './committee/committee.component';
import { DashboardComponent } from './dashboard/dashboard.component';
import {
  ContactCreate,
  ContactUpdate,
  LocationsComponent,
  RoomCreate,
  RoomUpdate,
  VenueCreate,
  VenueUpdate,
} from './locations/locations.component';
import {
  AvailabilityPayload,
  CandidateExamDayPayload,
  PlanningComponent,
  PlanningSettingsPayload,
} from './planning/planning.component';
import { PlanningWorkflowService } from './planning/planning-workflow.service';
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
import { AbsenceReportsComponent } from './absence-reports/absence-reports.component';
import { DemoScenariosComponent } from './demo-scenarios/demo-scenarios.component';
import { AboutComponent } from './about/about.component';
import { VenueWorkflowService } from './locations/venue-workflow.service';
import { MasterDataWorkflowService } from './master-data/master-data-workflow.service';
import { ApplicationWorkspaceService } from './shell/application-workspace.service';
import { UiFeedbackService } from './shell/ui-feedback.service';

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
    DemoScenariosComponent,
    ExamHalfYearsComponent,
    LocationsComponent,
    NotificationsComponent,
    AbsenceReportsComponent,
    AboutComponent,
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
  private readonly workspace = inject(ApplicationWorkspaceService);
  private readonly feedbackService = inject(UiFeedbackService);
  private readonly masterDataWorkflow = inject(MasterDataWorkflowService);
  private readonly planningWorkflow = inject(PlanningWorkflowService);
  private readonly venueWorkflow = inject(VenueWorkflowService);
  private readonly roundContext = inject(RoundContextService);
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
  protected readonly round = this.workspace.round;
  protected readonly summary = this.workspace.summary;
  protected readonly board = this.workspace.board;
  protected readonly masterData = this.workspace.masterData;
  protected readonly lastPlanningResult = this.planningWorkflow.lastResult;
  protected readonly planningProposal = this.planningWorkflow.proposal;
  protected readonly proposalEditorState = this.planningWorkflow.editorState;
  protected readonly proposalEditorError = this.planningWorkflow.editorError;
  protected readonly proposalEditorViolations = this.planningWorkflow.editorViolations;
  protected readonly candidateDayGenerationResult = this.planningWorkflow.candidateDayGeneration;
  protected readonly activeView = signal<AppView>('dashboard');
  protected readonly sidebarVisible = signal(
    typeof window === 'undefined' || window.innerWidth >= 768,
  );
  protected readonly selectedCommitteeId = this.workspace.selectedCommitteeId;
  protected readonly message = this.workspace.message;
  protected readonly loading = this.workspace.loading;
  protected readonly actionBusy = this.workspace.actionBusy;
  protected readonly geocodeCandidate = this.venueWorkflow.geocodeCandidate;
  protected readonly contextualRoundId = signal<number | null>(null);
  protected readonly contextualDayId = signal<number | null>(null);
  protected readonly contextualVenueId = signal<number | null>(null);
  protected readonly confirmedPlanEditRoundId = signal<number | null>(null);
  protected readonly applicationVersion = this.workspace.applicationVersion;
  protected readonly feedback = this.feedbackService.feedback;
  protected readonly masterDataError = this.workspace.masterDataError;
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
  protected readonly canWriteOwnAttendance = computed(() =>
    this.hasCapability('attendance:write-own'),
  );
  protected readonly canReportOwnAbsence = computed(() => this.hasCapability('absence:write-own'));
  protected readonly canEditConfirmedPlan = computed(() =>
    this.hasCapability('confirmed-plan:revise'),
  );
  protected readonly canManageVenueCreation = computed(
    () =>
      !this.demoSession() &&
      (this.auth.session()?.is_operator === true ||
        this.masterData()?.examVenuesCanCreate === true),
  );
  protected readonly canGenerateCandidateDays = this.planningWorkflow.canGenerateCandidateDays;
  protected readonly canCreateCandidateDay = this.planningWorkflow.canCreateCandidateDay;
  protected readonly canToggleCandidateDay = this.planningWorkflow.canToggleCandidateDay;
  protected readonly directAccessDenied = computed(() => !this.canAccessView(this.activeView()));

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
      'absence-reports': 'Ausfall und Ersatz',
      'demo-scenarios': 'Demo-Szenarien',
      about: 'Über lzug',
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
    if (this.activeView() === 'demo-scenarios') return 'Öffentliche Demo';
    if (this.activeView() === 'about') return 'Produktinformation';
    if (['notifications', 'absence-reports'].includes(this.activeView()))
      return 'Persönlicher Bereich';
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
    this.workspace.refresh();
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
    this.workspace.selectCommittee(id);
  }

  protected selectExamRound(id: number): void {
    this.planningWorkflow.resetForRoundChange();
    this.workspace.selectExamRound(id);
  }

  protected openSchedulingRound(action: SchedulingOverviewAction): void {
    this.lastPlanningResult.set(null);
    this.candidateDayGenerationResult.set(null);
    const area = action.target === 'confirmed-plan' ? 'confirmed-plans' : 'scheduling-overview';
    void this.router.navigateByUrl(`/${area}/${action.id}`);
  }

  protected openVenue(id: number): void {
    void this.router.navigateByUrl(`/locations/${id}`);
  }

  protected closeVenueDetail(): void {
    void this.router.navigateByUrl('/locations');
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
    this.feedbackService.dismiss();
  }

  protected demoRoleLabel(): string {
    const role = this.demoSession()?.demo_role;
    if (role === 'chair') return 'Vorsitz';
    if (role === 'replacement') return 'Angefragter Ersatzprüfer';
    return 'Eingeplanter Prüfer';
  }

  protected demoRoleTask(): string {
    const role = this.demoSession()?.demo_role;
    if (role === 'chair') return 'Koordination und Planrevision';
    if (role === 'replacement') return 'Eigene Ersatzanfrage beantworten';
    return 'Eigenen Ausfall melden';
  }

  protected hasCapability(capability: string): boolean {
    return this.auth.hasCapability(capability);
  }

  protected canAccessView(view: AppView): boolean {
    if (view === 'about') return true;
    if (!this.demoSession()) return view !== 'demo-scenarios';
    if (view === 'demo-scenarios') return true;
    if (view === 'dashboard') return true;
    if (view === 'notifications') return this.hasCapability('notifications:read-own');
    if (view === 'absence-reports') {
      return (
        this.hasCapability('absence:coordinate') ||
        this.hasCapability('absence:write-own') ||
        this.hasCapability('absence:respond-own')
      );
    }
    if (view === 'exam-half-years') return this.hasCapability('exam-half-years:read');
    if (['scheduling-overview', 'planning'].includes(view)) {
      return (
        this.hasCapability('availability:write-own') ||
        this.hasCapability('availability:coordinate') ||
        this.hasCapability('planning-settings:write')
      );
    }
    if (['confirmed-plans', 'exam-day'].includes(view)) {
      return (
        this.hasCapability('confirmed-plan:revise') ||
        this.hasCapability('absence:write-own') ||
        this.hasCapability('attendance:write-own') ||
        this.hasCapability('attendance:coordinate') ||
        this.hasCapability('exam-status:write') ||
        this.hasCapability('exam-result:read')
      );
    }
    return false;
  }

  protected switchDemoRole(): void {
    if (!this.demoSession() || this.roleSwitchBusy()) return;
    void this.router.navigateByUrl('/demo-scenarios');
  }

  protected requestCandidateDeletion(id: number, label: string): void {
    this.masterDataWorkflow.requestCandidateDeletion(id, label);
  }

  protected requestVenueDeletion(venue: ExamVenue): void {
    this.venueWorkflow.connect(this.locationsComponent);
    this.venueWorkflow.requestVenueDeletion(venue);
  }

  protected requestPlanConfirmation(): void {
    this.planningWorkflow.connect(this.planningComponent);
    this.planningWorkflow.requestPlanConfirmation();
  }

  protected createMember(payload: CommitteeMemberPayload): void {
    this.masterDataWorkflow.createMember(payload, this.committeeComponent);
  }

  protected createCandidate(payload: CandidatePayload): void {
    this.masterDataWorkflow.createCandidate(payload, this.candidatesComponent);
  }

  protected deleteCandidate(id: number, label: string): void {
    this.masterDataWorkflow.deleteCandidate(id, label);
  }

  protected updateCandidate(update: CandidateUpdate): void {
    this.masterDataWorkflow.updateCandidate(update, this.candidatesComponent);
  }

  protected createVenue(payload: VenueCreate): void {
    this.venueWorkflow.connect(this.locationsComponent);
    this.venueWorkflow.createVenue(payload);
  }

  protected updateVenue(update: VenueUpdate): void {
    this.venueWorkflow.connect(this.locationsComponent);
    this.venueWorkflow.updateVenue(update);
  }

  protected geocodeVenue(venue: ExamVenue): void {
    this.venueWorkflow.connect(this.locationsComponent);
    this.venueWorkflow.geocodeVenue(venue);
  }

  protected deleteVenue(venue: ExamVenue): void {
    this.venueWorkflow.connect(this.locationsComponent);
    this.venueWorkflow.deleteVenue(venue);
  }

  protected createRoom(command: RoomCreate): void {
    this.venueWorkflow.connect(this.locationsComponent);
    this.venueWorkflow.createRoom(command);
  }

  protected updateRoom(command: RoomUpdate): void {
    this.venueWorkflow.connect(this.locationsComponent);
    this.venueWorkflow.updateRoom(command);
  }

  protected deleteRoom(room: ExamRoom): void {
    this.venueWorkflow.connect(this.locationsComponent);
    this.venueWorkflow.deleteRoom(room);
  }

  protected retryVenueConsequences(auditId: number): void {
    this.venueWorkflow.connect(this.locationsComponent);
    this.venueWorkflow.retryVenueConsequences(auditId);
  }
  protected createContact(command: ContactCreate): void {
    this.venueWorkflow.connect(this.locationsComponent);
    this.venueWorkflow.createContact(command);
  }
  protected updateContact(command: ContactUpdate): void {
    this.venueWorkflow.connect(this.locationsComponent);
    this.venueWorkflow.updateContact(command);
  }
  protected deleteContact(contact: ExamVenueContact): void {
    this.venueWorkflow.connect(this.locationsComponent);
    this.venueWorkflow.deleteContact(contact);
  }
  protected requestPromotion(command: { venue: ExamVenue; reason: string }): void {
    this.venueWorkflow.connect(this.locationsComponent);
    this.venueWorkflow.requestPromotion(command);
  }
  protected decidePromotion(command: {
    venue: ExamVenue;
    decision: 'approve' | 'reject';
    reason: string;
  }): void {
    this.venueWorkflow.connect(this.locationsComponent);
    this.venueWorkflow.decidePromotion(command);
  }

  protected savePlanningSettings(payload: PlanningSettingsPayload): void {
    this.planningWorkflow.connect(this.planningComponent);
    this.planningWorkflow.savePlanningSettings(payload);
  }

  protected saveExamRound(payload: ExamRoundUpdate): void {
    this.planningWorkflow.connect(this.planningComponent);
    this.planningWorkflow.saveExamRound(payload);
  }

  protected requestAvailabilities(payload: AvailabilityRequest): void {
    this.planningWorkflow.connect(this.planningComponent);
    this.planningWorkflow.requestAvailabilities(payload);
  }

  protected createCandidateDay(payload: CandidateExamDayPayload): void {
    this.planningWorkflow.connect(this.planningComponent);
    this.planningWorkflow.createCandidateDay(payload);
  }

  protected generateCandidateDays(payload: PlanningSettingsPayload): void {
    this.planningWorkflow.connect(this.planningComponent);
    this.planningWorkflow.generateCandidateDays(payload);
  }

  protected toggleCandidateDay(day: CandidateExamDay): void {
    this.planningWorkflow.connect(this.planningComponent);
    this.planningWorkflow.toggleCandidateDay(day);
  }

  protected saveAvailability(payload: AvailabilityPayload): void {
    this.planningWorkflow.connect(this.planningComponent);
    this.planningWorkflow.saveAvailability(payload);
  }

  protected toggleMember(member: CommitteeMember): void {
    this.masterDataWorkflow.toggleMember(member);
  }

  protected generateProposal(): void {
    this.planningWorkflow.connect(this.planningComponent);
    this.planningWorkflow.generateProposal();
  }

  protected confirmPlan(): void {
    this.planningWorkflow.connect(this.planningComponent);
    this.planningWorkflow.confirmPlan();
  }

  protected loadPlanningProposal(): void {
    this.planningWorkflow.connect(this.planningComponent);
    this.planningWorkflow.loadPlanningProposal();
  }

  protected reloadPlanningProposal(): void {
    this.planningWorkflow.connect(this.planningComponent);
    this.planningWorkflow.reloadPlanningProposal();
  }

  protected savePlanningProposal(proposal: EditablePlanningProposal): void {
    this.planningWorkflow.connect(this.planningComponent);
    this.planningWorkflow.savePlanningProposal(proposal);
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
      'absence-reports': 'absence-reports',
      'demo-scenarios': 'demo-scenarios',
      about: 'about',
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
      'absence-reports': 'absence-reports',
      'demo-scenarios': 'demo-scenarios',
      about: 'about',
    };
    return views[segment ?? 'dashboard'] ?? 'dashboard';
  }

  private applyRoute(url: string, refreshWhenRoundChanges: boolean): void {
    this.activeView.set(this.viewFromUrl(url));
    const roundId = this.roundIdFromUrl(url);
    this.contextualRoundId.set(roundId);
    this.contextualDayId.set(this.dayIdFromUrl(url));
    this.contextualVenueId.set(this.venueIdFromUrl(url));
    this.confirmedPlanEditRoundId.set(this.confirmedPlanEditIdFromUrl(url));
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

  private confirmedPlanEditIdFromUrl(url: string): number | null {
    const segments = this.urlSegments(url);
    if (segments[0] !== 'confirmed-plans' || segments[2] !== 'edit') return null;
    const id = Number(segments[1]);
    return Number.isInteger(id) && id > 0 ? id : null;
  }

  private venueIdFromUrl(url: string): number | null {
    const segments = this.urlSegments(url);
    if (segments[0] !== 'locations' || !segments[1]) return null;
    const id = Number(segments[1]);
    return Number.isInteger(id) && id > 0 ? id : null;
  }

  private urlSegments(url: string): string[] {
    return url.split('?')[0].split('#')[0].split('/').filter(Boolean);
  }
}
