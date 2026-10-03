import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { signal, Type } from '@angular/core';
import { By } from '@angular/platform-browser';
import { provideRouter, Router } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';
import { TuiConfirmService } from '@taiga-ui/kit';
import { of, throwError } from 'rxjs';

import { App } from './app';
import { DashboardProjectionService } from './dashboard/dashboard-projection.service';
import { APPLICATION_SHELL_CONTEXT_PORT } from './shell/application-shell-context.port';
import type {
  VenueContact,
  VenueChangeImpact,
  VenueCreate,
  VenueRoomUpdate,
  VenueDuplicate,
  VenueUpdate,
} from './locations/locations.models';
import { HttpWorkspaceAdapter } from './api/http-workspace.adapter';
import { AuthService } from './auth/auth.service';
import type { AuthSession } from './auth/auth.models';
import { SessionScopeService } from './auth/session-scope.service';
import { RoundContextService } from './api/round-context.service';
import { routes } from './app.routes';
import { PlanningWorkflowService } from './planning/planning-workflow.service';
import { HttpPlanningAdapter } from './planning/http-planning.adapter';
import { toVenue } from './api/http-locations.mapper';
import { LOCATIONS_PORT, type LocationsPort } from './locations/locations.port';
import { PLANNING_PORT } from './planning/planning.port';
import { LocationsRouteComponent } from './routes/locations-route.component';
import { ApplicationWorkspaceService } from './shell/application-workspace.service';
import { MasterDataWorkflowService } from './master-data/master-data-workflow.service';
import { UiFeedbackService } from './shell/ui-feedback.service';
import { WORKSPACE_PORT } from './shell/workspace.port';
import { CONFIRMED_PLANS_PORT } from './confirmed-plans/confirmed-plans.port';
import { HttpConfirmedPlansAdapter } from './api/http-confirmed-plans.adapter';
import { VenueWorkflowService } from './locations/venue-workflow.service';
import { LocationsWorkspaceFacade } from './locations/locations-workspace.facade';
import { LOCATIONS_READ_PORT } from './locations/locations.port';
import { HttpLocationsReadAdapter } from './api/http-locations-read.adapter';
import { MASTER_DATA_PORT } from './master-data/master-data.port';
import { LifecycleService } from './runtime/lifecycle.service';
import {
  apiRootFixture,
  assignmentsFixture,
  availabilitiesFixture,
  candidateDaysFixture,
  candidateAssignmentsFixture,
  candidatesFixture,
  committeesFixture,
  examDaysFixture,
  examRoundFixture,
  examRoundsFixture,
  examSlotsFixture,
  foreignExamRoundFixture,
  locationsFixture,
  masterDataFixture,
  membersFixture,
  personsFixture,
  roundCandidatesFixture,
  summaryFixture,
} from './testing/fixtures';
describe('App', () => {
  let locationsPort: ReturnType<typeof createLocationsPortDouble>;
  let dashboard: {
    projection: ReturnType<typeof signal>;
    loading: ReturnType<typeof signal<boolean>>;
    error: ReturnType<typeof signal<boolean>>;
    locationRefreshError: ReturnType<typeof signal<boolean>>;
    refresh: ReturnType<typeof vi.fn>;
    refreshLocations: ReturnType<typeof vi.fn>;
  };
  beforeAll(() => {
    Object.defineProperty(HTMLSelectElement.prototype, 'readOnly', {
      configurable: true,
      get: () => false,
      set: () => undefined,
    });
  });

  beforeEach(async () => {
    locationsPort = createLocationsPortDouble();
    dashboard = {
      projection: signal({
        applicationVersion: 'test',
        round: examRoundFixture,
        summary: summaryFixture,
        board: {
          members: [],
          locations: locationsFixture,
          candidates: [],
          candidateDays: [],
          availabilities: [],
          days: [],
        },
      }),
      loading: signal(false),
      error: signal(false),
      locationRefreshError: signal(false),
      refresh: vi.fn(),
      refreshLocations: vi.fn(),
    };
    const session = signal<ReturnType<AuthService['session']>>(null);
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter(routes),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: PLANNING_PORT, useClass: HttpPlanningAdapter },
        { provide: LOCATIONS_PORT, useValue: locationsPort },
        { provide: LOCATIONS_READ_PORT, useClass: HttpLocationsReadAdapter },
        { provide: WORKSPACE_PORT, useClass: HttpWorkspaceAdapter },
        { provide: CONFIRMED_PLANS_PORT, useClass: HttpConfirmedPlansAdapter },
        {
          provide: MASTER_DATA_PORT,
          useValue: {
            loadCandidateWorkspace: vi.fn(() =>
              of({
                candidates: [
                  {
                    candidate: {
                      id: 4,
                      firstName: 'Ada',
                      lastName: 'Lovelace',
                      examNumber: 'EX-4',
                      specialization: 'IT',
                      trainingCompany: 'Company',
                    },
                  },
                ],
                assignments: [],
                examRounds: [],
                committees: [],
                activeRound: null,
              }),
            ),
            loadCommitteeWorkspace: vi.fn(() => of({ committees: [], members: [], persons: [] })),
            createCandidate: vi.fn(() => of({})),
            updateCandidate: vi.fn(() => of({})),
            deleteCandidate: vi.fn(() => of(undefined)),
            createCommitteeMember: vi.fn(() => of({})),
            updateCommitteeMember: vi.fn(() => of({})),
          },
        },
        { provide: DashboardProjectionService, useValue: dashboard },
        {
          provide: APPLICATION_SHELL_CONTEXT_PORT,
          useValue: {
            load: vi.fn((roundId: number) =>
              of({
                applicationVersion: '0.1.0',
                roundId,
                halfYear: 'Winter 2026',
                round: `Runde ${roundId}`,
                committee: roundId === 2 ? 'Fremdausschuss Feenwald' : 'Prüfungsausschuss',
                status: 'planning',
              }),
            ),
          },
        },
        provideTaiga({ scrollbars: 'native' }),
        TuiConfirmService,
        { provide: LifecycleService, useValue: { ready: signal(true), check: () => of(true) } },
        {
          provide: AuthService,
          useValue: {
            state: signal('authenticated'),
            session,
            hasCapability: (capability: string) => {
              const capabilities = session()?.capabilities;
              return capabilities == null || capabilities.includes(capability);
            },
            initialize: () => of(true),
            markAnonymous: vi.fn(),
            logout: () => of(undefined),
          },
        },
      ],
    }).compileComponents();
  });

  afterEach(() => {
    const http = TestBed.inject(HttpTestingController);
    http.match('/api/locations').forEach((request) => request.flush(locationsFixture));
    http.verify();
  });

  it('should render the exam round dashboard', async () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);

    flushDashboardRequests(http);

    fixture.detectChanges();
    await TestBed.inject(Router).navigateByUrl('/dashboard');
    await stabilizeRoute(fixture);

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('h1')?.textContent).toContain('Übersicht');
    expect(compiled.textContent).toContain('Terminorganisationen öffnen');
    expect(compiled.textContent).toContain('Aktueller Prüfungskontext');
    expect(compiled.textContent).toContain('Winter 2026');
    expect(compiled.textContent).toContain('Hauptausschuss Athen');
    expect(compiled.textContent).toContain('Version 0.1.0');
  });

  it('refreshes the dashboard after a later login', () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);

    const auth = TestBed.inject(AuthService) as unknown as {
      state: { set(value: 'anonymous' | 'authenticated'): void };
    };
    auth.state.set('anonymous');
    fixture.detectChanges();
    auth.state.set('authenticated');
    fixture.detectChanges();

    flushDashboardRequests(http);
  });

  it('reloads the workspace after an authenticated demo role changes', () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);

    const auth = TestBed.inject(AuthService) as unknown as {
      session: { set(value: AuthSession): void };
    };
    const scope = TestBed.inject(SessionScopeService);
    const examiner: AuthSession = {
      authenticated: true,
      account_id: 4,
      person_id: 9,
      committee_member_id: 12,
      is_operator: false,
      capabilities: ['availability:write-own'],
      demo_role: 'examiner',
    };
    const chair: AuthSession = {
      ...examiner,
      capabilities: ['availability:coordinate'],
      demo_role: 'chair',
    };

    auth.session.set(examiner);
    scope.establish(examiner);
    auth.session.set(chair);
    scope.establish(chair);

    flushDashboardRequests(http);
    fixture.destroy();
  });

  it('keeps the authenticated shell landmark outside auth routes', async () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);

    const auth = TestBed.inject(AuthService) as unknown as {
      state: { set(value: 'anonymous' | 'authenticated'): void };
    };
    auth.state.set('anonymous');

    fixture.detectChanges();
    await TestBed.inject(Router).navigateByUrl('/login');
    await stabilizeRoute(fixture);

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelectorAll('main')).toHaveLength(1);
    expect(compiled.querySelector('main.auth-page')).not.toBeNull();
    expect(compiled.querySelector('main.app-content')).toBeNull();
  });

  it('should expose the sidebar visibility through accessible toggle state', () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);
    fixture.detectChanges();

    const app = fixture.componentInstance as unknown as {
      sidebarVisible: {
        (): boolean;
        set(value: boolean): void;
      };
    };
    const toggle = () =>
      (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
        '.app-sidebar-toggle',
      );
    const sidebar = () =>
      (fixture.nativeElement as HTMLElement).querySelector<HTMLElement>('.app-sidebar');

    app.sidebarVisible.set(true);
    fixture.detectChanges();

    expect(toggle()?.getAttribute('aria-expanded')).toBe('true');
    expect(toggle()?.getAttribute('aria-label')).toBe('Navigation schließen');
    expect(sidebar()?.hasAttribute('inert')).toBe(false);
    expect(sidebar()?.hasAttribute('aria-hidden')).toBe(false);

    app.sidebarVisible.set(false);
    fixture.detectChanges();

    expect(toggle()?.getAttribute('aria-expanded')).toBe('false');
    expect(toggle()?.getAttribute('aria-label')).toBe('Navigation öffnen');
    expect(sidebar()?.hasAttribute('inert')).toBe(true);
    expect(sidebar()?.getAttribute('aria-hidden')).toBe('true');
  });

  it('should update the selected committee', () => {
    TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);

    const workflow = TestBed.inject(MasterDataWorkflowService);
    workflow.selectedCommitteeId.set(2);

    expect(workflow.selectedCommitteeId()).toBe(2);
  });

  it('should refresh the visible context after selecting another exam round', () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);

    TestBed.inject(ApplicationWorkspaceService).selectExamRound(2);
    flushDashboardRequests(http, foreignExamRoundFixture);
    fixture.detectChanges();

    expect(TestBed.inject(RoundContextService).roundId()).toBe(2);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Fremdausschuss Feenwald');
  });

  it('should ask before deleting a candidate', async () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);
    fixture.detectChanges();

    await TestBed.inject(Router).navigateByUrl('/candidates');
    fixture.detectChanges();
    const confirm = TestBed.inject(TuiConfirmService);
    const confirmSpy = vi.spyOn(confirm, 'withConfirm').mockReturnValue(of(false));

    clickButton(fixture, 'Löschen');

    expect(confirmSpy).toHaveBeenCalled();
    expect(vi.mocked(confirmSpy).mock.lastCall?.[0]).toEqual(
      expect.objectContaining({
        label: 'Ada Lovelace löschen?',
        data: expect.objectContaining({ yes: 'Ada Lovelace löschen' }),
      }),
    );
    expect(http.match((request) => request.method === 'DELETE').length).toBe(0);
  });

  it('should keep round-specific workflow URLs in their contextual frame', async () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    const router = TestBed.inject(Router);
    flushDashboardRequests(http);

    await router.navigateByUrl('/scheduling-overview/1');
    fixture.detectChanges();

    expect(router.url).toBe('/scheduling-overview/1');
    expect((fixture.nativeElement as HTMLElement).querySelector('h1')?.textContent).toContain(
      'Terminorganisation',
    );
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Aktueller Prüfungskontext',
    );
  });

  it('updates title and focus from route data after browser navigation', async () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    const router = TestBed.inject(Router);
    flushDashboardRequests(http);

    await router.navigateByUrl('/about');
    await stabilizeRoute(fixture);

    const heading = (fixture.nativeElement as HTMLElement).querySelector('h1');
    expect(heading?.textContent).toContain('Über lzug');
    expect(document.title).toBe('Über lzug · lzug');
    expect(document.activeElement).toBe(heading);
  });

  it('should expose operation errors as a consistent alert', () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);

    const app = fixture.componentInstance as unknown as { dismissFeedback: () => void };
    TestBed.inject(UiFeedbackService).notify(
      'error',
      'Nicht gespeichert',
      'Bitte Eingaben prüfen.',
    );
    fixture.detectChanges();

    const alert = (fixture.nativeElement as HTMLElement).querySelector('.app-feedback');
    expect(alert?.getAttribute('role')).toBe('alert');
    expect(alert?.textContent).toContain('Bitte Eingaben prüfen.');
    expect(alert?.querySelector('.app-feedback-icon')).toBeTruthy();

    app.dismissFeedback();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('.app-feedback')).toBeNull();
  });

  it('should keep development-only prototype content out of the application shell', () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).not.toContain('Entwicklung');
    expect(element.textContent).not.toContain('Taiga-Prototyp');
    expect(element.querySelector('.app-header-title')?.textContent).toContain('Prüfungsverwaltung');
    expect(element.querySelector('h1')?.textContent).toContain('Übersicht');
    expect(element.textContent).toContain('Daten synchronisiert');
  });

  it('shows the active demo identity and protects role-incompatible routes', async () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    const router = TestBed.inject(Router);
    flushDashboardRequests(http);

    const auth = TestBed.inject(AuthService) as unknown as {
      session: {
        set(value: {
          authenticated: boolean;
          account_id: number;
          person_id: number;
          committee_member_id: number;
          is_operator: boolean;
          demo_role: 'chair' | 'examiner' | 'replacement';
          display_name: string;
          capabilities: string[];
        }): void;
      };
    };
    auth.session.set({
      authenticated: true,
      account_id: 2,
      person_id: 3,
      committee_member_id: 3,
      is_operator: false,
      demo_role: 'examiner',
      display_name: 'Peter Quince',
      capabilities: ['absence:write-own', 'notifications:read-own', 'calendar:read-own'],
    });
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Peter Quince');
    expect(element.textContent).toContain('Eingeplanter Prüfer');
    expect(element.textContent).toContain('Rolle wechseln');
    expect(element.querySelector('a[href="/scheduling-overview"]')).toBeNull();
    expect(element.querySelector('a[href="/confirmed-plans"]')).not.toBeNull();
    expect(element.querySelector('a[href="/candidates"]')).toBeNull();
    expect(element.textContent).not.toContain('Prüfungsausschüsse');

    await router.navigateByUrl('/candidates');
    fixture.detectChanges();

    expect(element.textContent).toContain(
      'Dieser Demo-Bereich ist für Ihre Rolle nicht freigegeben.',
    );
    expect(element.querySelector('app-candidates')).toBeNull();
  });

  it('guards demo mutations by the effective capability set', () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);

    const auth = TestBed.inject(AuthService) as unknown as {
      session: {
        set(value: {
          authenticated: boolean;
          account_id: number;
          person_id: number;
          committee_member_id: number;
          is_operator: boolean;
          demo_role: 'chair' | 'examiner' | 'replacement';
          display_name: string;
          capabilities: string[];
        }): void;
      };
    };
    auth.session.set({
      authenticated: true,
      account_id: 2,
      person_id: 3,
      committee_member_id: 3,
      is_operator: false,
      demo_role: 'examiner',
      display_name: 'Peter Quince',
      capabilities: ['absence:write-own', 'notifications:read-own', 'calendar:read-own'],
    });
    fixture.detectChanges();

    const app = fixture.componentInstance as unknown as {
      demoRoleLabel(): string;
      demoRoleTask(): string;
      canAccessView(view: string): boolean;
      switchDemoRole(): void;
      roleSwitchBusy(): boolean;
    };
    const planning = TestBed.inject(PlanningWorkflowService);

    expect(app.demoRoleLabel()).toBe('Eingeplanter Prüfer');
    expect(app.demoRoleTask()).toBe('Eigenen Ausfall melden');
    expect(app.canAccessView('planning')).toBe(false);
    expect(app.canAccessView('confirmed-plans')).toBe(true);
    expect(app.canAccessView('candidates')).toBe(false);

    planning.savePlanningSettings(undefined as never);
    planning.saveExamRound(undefined as never);
    planning.requestAvailabilities(undefined as never);
    planning.createCandidateDay(undefined as never);
    planning.generateCandidateDays(undefined as never);
    planning.toggleCandidateDay(undefined as never);
    planning.saveAvailability({
      committee_member_id: 99,
      candidate_exam_day_id: 1,
      availability: 'full_day',
    } as never);
    planning.generateProposal();
    planning.savePlanningProposal(undefined as never);
    planning.confirmPlan();

    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Aktion für diese Rolle nicht verfügbar',
    );

    auth.session.set({
      authenticated: true,
      account_id: 1,
      person_id: 1,
      committee_member_id: 1,
      is_operator: false,
      demo_role: 'chair',
      display_name: 'Vorsitz Teststadt',
      capabilities: [
        'absence:coordinate',
        'confirmed-plan:revise',
        'notifications:read-own',
        'calendar:read-own',
      ],
    });
    fixture.detectChanges();
    expect(app.demoRoleLabel()).toBe('Vorsitz');
    expect(app.demoRoleTask()).toBe('Koordination und Planrevision');
    expect(app.canAccessView('planning')).toBe(false);
    expect(app.canAccessView('exam-day')).toBe(true);

    app.switchDemoRole();
    expect(app.roleSwitchBusy()).toBe(false);
  });

  it('checks venue duplicates and future impact before persisting aggregates', () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);
    const workflow = TestBed.inject(VenueWorkflowService);
    const venue = toVenue(masterDataFixture.examVenues[0]);
    const create: VenueCreate = {
      scope: 'committee',
      committeeId: 1,
      name: 'Prüfungszentrum West',
      street: 'Testweg 2',
      postalCode: '20095',
      city: 'Hamburg',
      country: 'Deutschland',
      accessibilityStatus: 'confirmed',
      isAccessible: true,
      isActive: true,
    };
    workflow.createVenue(create);
    expect(locationsPort.checkDuplicates).toHaveBeenCalledWith(create);
    expect(locationsPort.createVenue).toHaveBeenCalledWith({
      ...create,
      duplicatesReviewed: false,
    });
    const update: VenueUpdate = {
      id: venue.id,
      payload: { expectedRevision: venue.revision, name: 'Prüfungszentrum Neu' },
    };
    workflow.updateVenue(update);
    expect(locationsPort.getVenueChangeImpact).toHaveBeenCalledWith(venue.id, update.payload);
    expect(locationsPort.updateVenue).toHaveBeenCalledWith({
      ...update,
      confirmFutureAssignments: false,
      duplicatesReviewed: false,
    });
    const roomUpdate: VenueRoomUpdate = {
      id: venue.rooms[0].id,
      payload: { expectedRevision: venue.rooms[0].revision, name: 'A-102' },
    };
    workflow.updateRoom(roomUpdate);
    expect(locationsPort.getRoomChangeImpact).toHaveBeenCalledWith(
      roomUpdate.id,
      roomUpdate.payload,
    );
    expect(locationsPort.updateRoom).toHaveBeenCalledWith({
      ...roomUpdate,
      confirmFutureAssignments: false,
    });
    locationsPort.checkDuplicates.mockReturnValueOnce(throwError(() => new Error('unavailable')));
    workflow.createVenue(create);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Dublettenprüfung fehlgeschlagen',
    );
    vi.spyOn(TestBed.inject(TuiConfirmService), 'withConfirm').mockReturnValue(of(false));
    locationsPort.checkDuplicates.mockReturnValueOnce(
      of([{ id: 9, name: 'Prüfungszentrum West', scope: 'global', address: 'Testweg 2, Hamburg' }]),
    );
    workflow.createVenue(create);
    expect(locationsPort.createVenue).toHaveBeenCalledTimes(1);
    locationsPort.getVenueChangeImpact.mockReturnValueOnce(of(venueImpact(2, true)));
    workflow.updateVenue(update);
    expect(locationsPort.updateVenue).toHaveBeenCalledTimes(1);
  });
  it('keeps explicit geocoding candidates separate from venue data on success and failure', () => {
    TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);
    const workflow = TestBed.inject(VenueWorkflowService);
    const venue = toVenue(masterDataFixture.examVenues[0]);
    workflow.geocodeVenue(venue);
    expect(workflow.geocodeCandidate()).toEqual({
      venueId: venue.id,
      latitude: 53.55,
      longitude: 9.99,
      source: 'test',
    });
    locationsPort.geocodeVenue.mockReturnValueOnce(throwError(() => new Error('unavailable')));
    workflow.geocodeVenue(venue);
    expect(workflow.geocodeCandidate()?.latitude).toBe(53.55);
    const update: VenueUpdate = {
      id: venue.id,
      payload: {
        expectedRevision: venue.revision,
        latitude: 53.55,
        longitude: 9.99,
        coordinateStatus: 'confirmed',
        coordinateSource: 'nominatim',
      },
    };
    workflow.updateVenue(update);
    expect(workflow.geocodeCandidate()).toBeNull();
    workflow.geocodeVenue(venue);
    locationsPort.updateVenue.mockReturnValueOnce(throwError(() => new Error('unavailable')));
    workflow.updateVenue(update);
    expect(workflow.geocodeCandidate()).not.toBeNull();
  });
  it('routes into and out of the selected venue detail', async () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    const router = TestBed.inject(Router);
    flushDashboardRequests(http);
    await router.navigateByUrl('/locations');
    fixture.detectChanges();
    flushLocationRead(http);
    await stabilizeRoute(fixture);
    const route = routeComponent(fixture, LocationsRouteComponent) as unknown as {
      openVenue(id: number): void;
      closeDetail(): void;
      locations: LocationsWorkspaceFacade;
    };

    const locations = route.locations;
    const snapshot = locations.snapshot();
    expect(snapshot).not.toBeNull();
    fixture.detectChanges();
    expect(locations.snapshot()).toBe(snapshot);
    const workspace = TestBed.inject(ApplicationWorkspaceService);
    const currentMasterData = workspace.masterData();
    expect(currentMasterData).not.toBeNull();
    workspace.masterData.set({
      ...currentMasterData!,
      examVenues: [
        ...currentMasterData!.examVenues,
        { ...currentMasterData!.examVenues[0], id: 999 },
      ],
    });
    expect(locations.snapshot()).toBe(snapshot);

    route.openVenue(masterDataFixture.examVenues[0].id);
    await fixture.whenStable();
    fixture.detectChanges();
    flushLocationReads(http);
    await stabilizeRoute(fixture);
    expect(router.url).toBe(`/locations/${masterDataFixture.examVenues[0].id}`);
    expect((fixture.componentInstance as unknown as { breadcrumb(): string }).breadcrumb()).toBe(
      'Globale Bereiche',
    );

    const detailRoute = routeComponent(fixture, LocationsRouteComponent) as unknown as {
      closeDetail(): void;
    };
    detailRoute.closeDetail();
    await fixture.whenStable();
    fixture.detectChanges();
    flushLocationReads(http);
    await stabilizeRoute(fixture);
    expect(router.url).toBe('/locations');
  });

  it('covers confirmed venue actions and their non-mutating failure paths', () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);
    const workflow = TestBed.inject(VenueWorkflowService);
    const venue = toVenue(masterDataFixture.examVenues[0]);
    locationsPort.deleteVenue.mockReturnValue(throwError(() => new Error('expected')));
    locationsPort.createRoom.mockReturnValue(throwError(() => new Error('expected')));
    locationsPort.deleteRoom.mockReturnValue(throwError(() => new Error('expected')));
    locationsPort.createContact.mockReturnValue(throwError(() => new Error('expected')));
    locationsPort.updateContact.mockReturnValue(throwError(() => new Error('expected')));
    locationsPort.deleteContact.mockReturnValue(throwError(() => new Error('expected')));
    locationsPort.requestPromotion.mockReturnValue(throwError(() => new Error('expected')));
    locationsPort.decidePromotion.mockReturnValue(throwError(() => new Error('expected')));
    vi.spyOn(TestBed.inject(TuiConfirmService), 'withConfirm')
      .mockReturnValueOnce(of(false))
      .mockReturnValue(of(true));
    workflow.requestVenueDeletion(venue);
    expect(locationsPort.deleteVenue).not.toHaveBeenCalled();
    locationsPort.deleteVenue.mockReturnValueOnce(throwError(() => new Error('in use')));
    workflow.deleteVenue(venue);
    expect(locationsPort.deleteVenue).toHaveBeenCalledWith(venue.id, venue.revision);
    locationsPort.createVenue.mockReturnValueOnce(throwError(() => new Error('unavailable')));
    workflow.createVenue({
      scope: 'committee',
      committeeId: 1,
      name: 'Ort',
      street: 'Weg 1',
      postalCode: '20095',
      city: 'Hamburg',
      country: 'Deutschland',
      accessibilityStatus: 'confirmed',
      isAccessible: true,
      isActive: true,
    });
    expect(locationsPort.createVenue).toHaveBeenCalledTimes(1);
    const update: VenueRoomUpdate = {
      id: venue.rooms[0].id,
      payload: { expectedRevision: venue.rooms[0].revision, name: 'A-102' },
    };
    locationsPort.getRoomChangeImpact.mockReturnValueOnce(of(venueImpact(1, true)));
    locationsPort.updateRoom.mockReturnValueOnce(throwError(() => new Error('conflict')));
    workflow.updateRoom(update);
    expect(locationsPort.updateRoom).toHaveBeenCalledWith({
      ...update,
      confirmFutureAssignments: true,
    });
    locationsPort.getRoomChangeImpact.mockReturnValueOnce(
      throwError(() => new Error('unavailable')),
    );
    workflow.updateRoom(update);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Auswirkungsprüfung fehlgeschlagen',
    );
  });
  it('routes every nested venue command through the locations port', () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);
    const workflow = TestBed.inject(VenueWorkflowService);
    const venue = toVenue(masterDataFixture.examVenues[0]);
    locationsPort.deleteVenue.mockReturnValue(throwError(() => new Error('expected')));
    locationsPort.createRoom.mockReturnValue(throwError(() => new Error('expected')));
    locationsPort.deleteRoom.mockReturnValue(throwError(() => new Error('expected')));
    locationsPort.createContact.mockReturnValue(throwError(() => new Error('expected')));
    locationsPort.updateContact.mockReturnValue(throwError(() => new Error('expected')));
    locationsPort.deleteContact.mockReturnValue(throwError(() => new Error('expected')));
    locationsPort.requestPromotion.mockReturnValue(throwError(() => new Error('expected')));
    locationsPort.decidePromotion.mockReturnValue(throwError(() => new Error('expected')));
    const room = venue.rooms[0];
    const contact: VenueContact = {
      id: 4,
      venueId: venue.id,
      label: 'Empfang',
      role: null,
      phone: '+49 40 123',
      email: null,
      availabilityNotes: null,
      isActive: true,
      revision: 3,
      roomIds: [],
    };
    workflow.deleteVenue(venue);
    workflow.createRoom({
      venueId: venue.id,
      payload: { name: 'B-202', capacity: 12, isActive: true },
    });
    workflow.deleteRoom(room);
    workflow.createContact({
      venueId: venue.id,
      payload: {
        label: 'Empfang',
        email: null,
        phone: '123',
        availabilityNotes: null,
        isActive: true,
      },
    });
    workflow.updateContact({
      id: contact.id,
      payload: { expectedRevision: contact.revision, label: 'Neu' },
    });
    workflow.deleteContact(contact);
    workflow.requestPromotion({ venue, reason: 'Bundesweit geeignet' });
    workflow.decidePromotion({ venue, decision: 'approve', reason: 'Geprüft' });
    expect(locationsPort.deleteVenue).toHaveBeenCalledWith(venue.id, venue.revision);
    expect(locationsPort.createRoom).toHaveBeenCalledWith({
      venueId: venue.id,
      payload: { name: 'B-202', capacity: 12, isActive: true },
    });
    expect(locationsPort.deleteRoom).toHaveBeenCalledWith(room.id, room.revision);
    expect(locationsPort.createContact).toHaveBeenCalledOnce();
    expect(locationsPort.updateContact).toHaveBeenCalledWith({
      id: contact.id,
      payload: { expectedRevision: contact.revision, label: 'Neu' },
    });
    expect(locationsPort.deleteContact).toHaveBeenCalledWith(contact.id, contact.revision);
    expect(locationsPort.requestPromotion).toHaveBeenCalledWith(
      venue.id,
      venue.revision,
      'Bundesweit geeignet',
    );
    expect(locationsPort.decidePromotion).toHaveBeenCalledWith(
      venue.id,
      venue.revision,
      'approve',
      'Geprüft',
    );
    fixture.detectChanges();
  });
});

function clickButton(fixture: ComponentFixture<App>, label: string): void {
  const button = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('button')).find(
    (item) => item.textContent?.includes(label),
  );
  expect(button).toBeDefined();
  button?.click();
}

async function stabilizeRoute(fixture: ComponentFixture<App>): Promise<void> {
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
}

function routeComponent<T>(fixture: ComponentFixture<App>, component: Type<T>): T {
  const debugElement = fixture.debugElement.query(By.directive(component));
  expect(debugElement).not.toBeNull();
  return debugElement.componentInstance as T;
}

function createLocationsPortDouble() {
  const venue = toVenue(masterDataFixture.examVenues[0]);
  const port = {
    checkDuplicates: vi.fn(() => of([] as VenueDuplicate[])),
    getVenueChangeImpact: vi.fn(() => of(venueImpact(0, false))),
    getRoomChangeImpact: vi.fn(() => of(venueImpact(0, false))),
    createVenue: vi.fn(() => of(venue)),
    updateVenue: vi.fn(() => of(venue)),
    geocodeVenue: vi.fn(() => of({ latitude: 53.55, longitude: 9.99, source: 'test' })),
    deleteVenue: vi.fn(() => of(undefined)),
    createRoom: vi.fn(() => of(venue.rooms[0])),
    updateRoom: vi.fn(() => of(venue.rooms[0])),
    deleteRoom: vi.fn(() => of(undefined)),
    retryConsequences: vi.fn(() => of({})),
    createContact: vi.fn(() => of(venue.contacts[0])),
    updateContact: vi.fn(() => of(venue.contacts[0])),
    deleteContact: vi.fn(() => of(undefined)),
    requestPromotion: vi.fn(() => of({})),
    decidePromotion: vi.fn(() => of(venue)),
  } satisfies LocationsPort;
  return port;
}

function venueImpact(count: number, requiresConfirmation: boolean): VenueChangeImpact {
  return {
    count,
    dateFrom: count ? '2026-11-01' : null,
    dateTo: count ? '2026-11-30' : null,
    requiresConfirmation,
    calendar: { eventCount: 0, fields: [] },
    notifications: { recipientCount: 0, fields: [] },
  };
}

function flushDashboardRequests(http: HttpTestingController, round = examRoundFixture): void {
  const roundId = round.id;
  http.expectOne('/api').flush(apiRootFixture);
  http.expectOne(`/api/exam-rounds/${roundId}`).flush(round);
  http.expectOne(`/api/round-summary?round_id=${roundId}`).flush({
    ...summaryFixture,
    round: {
      ...summaryFixture.round,
      id: roundId,
      name: round.name,
      committee_name:
        committeesFixture.find((committee) => committee.id === round.committee_id)?.name ?? '',
    },
  });
  http
    .expectOne(`/api/exam-days?round_id=${roundId}`)
    .flush({ items: examDaysFixture, _links: {} });
  http.expectOne('/api/exam-slots').flush({ items: examSlotsFixture, _links: {} });
  http.expectOne('/api/exam-day-assignments').flush({ items: assignmentsFixture, _links: {} });
  const candidateRequests = http.match('/api/candidates');
  expect(candidateRequests.length).toBe(2);
  candidateRequests.forEach((request) => request.flush({ items: candidatesFixture, _links: {} }));

  const roundCandidateRequests = http.match(
    `/api/round-candidates?round_id=${roundId}&is_active=1`,
  );
  expect(roundCandidateRequests.length).toBe(2);
  roundCandidateRequests.forEach((request) =>
    request.flush({ items: roundCandidatesFixture, _links: {} }),
  );
  http.expectOne(`/api/candidate-exam-days?round_id=${roundId}`).flush({
    items: candidateDaysFixture,
    _links: {},
  });
  http.expectOne(`/api/member-availabilities?round_id=${roundId}`).flush({
    items: availabilitiesFixture,
    _links: {},
  });

  const memberRequests = http.match('/api/members');
  expect(memberRequests.length).toBe(2);
  memberRequests.forEach((request) => request.flush({ items: membersFixture, _links: {} }));

  http.expectOne('/api/persons').flush({ items: personsFixture, _links: {} });

  http.expectOne('/api/committees').flush({
    items: committeesFixture,
    _links: {},
  });
  http.expectOne('/api/exam-half-years').flush({
    items: [{ id: 1, season: 'winter', year: 2026, status: 'active' }],
    _links: {},
  });
  http.expectOne('/api/exam-rounds').flush({ items: examRoundsFixture, _links: {} });
  http.expectOne('/api/candidate-committee-assignments').flush({
    items: candidateAssignmentsFixture,
    _links: {},
  });
  http.expectOne('/api/exam-venues').flush({
    items: masterDataFixture.examVenues,
    _links: {},
  });

  const locationRequests = http.match('/api/locations');
  expect(locationRequests.length).toBe(2);
  locationRequests.forEach((request) => request.flush({ items: locationsFixture, _links: {} }));
}

function flushLocationRead(http: HttpTestingController): void {
  const committees = http.match('/api/committees');
  expect(committees).toHaveLength(1);
  committees.forEach((request) =>
    request.flush({ items: masterDataFixture.committees, _links: {} }),
  );
  const requests = http.match('/api/exam-venues');
  expect(requests).toHaveLength(1);
  requests.forEach((request) =>
    request.flush({
      items: masterDataFixture.examVenues,
      _links: { create: { href: '/api/exam-venues' } },
    }),
  );
}

function flushLocationReads(http: HttpTestingController): void {
  const committees = http.match('/api/committees');
  committees.forEach((request) =>
    request.flush({ items: masterDataFixture.committees, _links: {} }),
  );
  const requests = http.match('/api/exam-venues');
  requests.forEach((request) => request.flush({ items: masterDataFixture.examVenues, _links: {} }));
}
