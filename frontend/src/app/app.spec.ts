import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { signal, Type } from '@angular/core';
import { By } from '@angular/platform-browser';
import { provideRouter, Router } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';
import { TuiConfirmService } from '@taiga-ui/kit';
import { of } from 'rxjs';

import { App } from './app';
import { ExamRoom, ExamVenue, ExamVenueContact } from './api/api.models';
import { AuthService } from './auth/auth.service';
import {
  ContactCreate,
  ContactUpdate,
  RoomCreate,
  RoomUpdate,
  VenueCreate,
  VenueUpdate,
} from './locations/locations.component';
import { RoundContextService } from './api/round-context.service';
import { routes } from './app.routes';
import { PlanningWorkflowService } from './planning/planning-workflow.service';
import { LocationsRouteComponent } from './routes/locations-route.component';
import { ApplicationWorkspaceService } from './shell/application-workspace.service';
import { UiFeedbackService } from './shell/ui-feedback.service';
import { VenueWorkflowService } from './locations/venue-workflow.service';
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
  beforeAll(() => {
    Object.defineProperty(HTMLSelectElement.prototype, 'readOnly', {
      configurable: true,
      get: () => false,
      set: () => undefined,
    });
  });

  beforeEach(async () => {
    const session = signal<ReturnType<AuthService['session']>>(null);
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter(routes),
        provideHttpClient(),
        provideHttpClientTesting(),
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
              return capabilities === undefined || capabilities.includes(capability);
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
    TestBed.inject(HttpTestingController).verify();
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

    const workspace = TestBed.inject(ApplicationWorkspaceService);
    workspace.selectCommittee(2);

    expect(workspace.selectedCommitteeId()).toBe(2);
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
        label: 'Hermia von Athen löschen?',
        data: expect.objectContaining({ yes: 'Hermia von Athen löschen' }),
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
    const workflow = TestBed.inject(VenueWorkflowService) as unknown as {
      createVenue(payload: VenueCreate): void;
      updateVenue(update: VenueUpdate): void;
      updateRoom(update: RoomUpdate): void;
    };
    const workspace = TestBed.inject(ApplicationWorkspaceService);
    const venue = masterDataFixture.examVenues[0];
    const create: VenueCreate = {
      scope: 'committee',
      committee_id: 1,
      name: 'Prüfungszentrum West',
      street: 'Testweg 2',
      postal_code: '20095',
      city: 'Hamburg',
      country: 'Deutschland',
      accessibility_status: 'confirmed',
      is_accessible: true,
      is_active: true,
    };

    workflow.createVenue(create);
    expect(workspace.actionBusy()).toBe(true);
    const duplicateCheck = http.expectOne('/api/exam-venues/duplicate-check');
    expect(duplicateCheck.request.method).toBe('POST');
    duplicateCheck.flush({ items: [] });
    const createRequest = http.expectOne('/api/exam-venues');
    expect(createRequest.request.body).toEqual({ ...create, duplicates_reviewed: false });
    createRequest.flush({ ...venue, id: 7, name: create.name });
    flushDashboardRequests(http);
    expect(workspace.actionBusy()).toBe(false);

    const update: VenueUpdate = {
      id: venue.id,
      payload: { expected_revision: venue.revision, name: 'Prüfungszentrum Neu' },
    };
    workflow.updateVenue(update);
    const venueImpact = http.expectOne(`/api/exam-venues/${venue.id}/change-impact`);
    expect(venueImpact.request.method).toBe('POST');
    expect(venueImpact.request.body).toEqual(update.payload);
    venueImpact.flush({ count: 0 });
    http.expectOne('/api/exam-venues/duplicate-check').flush({ items: [] });
    const updateRequest = http.expectOne(`/api/exam-venues/${venue.id}`);
    expect(updateRequest.request.body).toEqual({
      ...update.payload,
      confirm_future_assignments: false,
      duplicates_reviewed: false,
    });
    updateRequest.flush({ ...venue, name: 'Prüfungszentrum Neu', revision: venue.revision + 1 });
    flushDashboardRequests(http);

    workflow.updateRoom({
      id: venue.rooms[0].id,
      payload: { expected_revision: venue.rooms[0].revision, name: 'A-102' },
    });
    const roomImpact = http.expectOne(`/api/exam-rooms/${venue.rooms[0].id}/change-impact`);
    expect(roomImpact.request.method).toBe('POST');
    expect(roomImpact.request.body).toEqual({
      expected_revision: venue.rooms[0].revision,
      name: 'A-102',
    });
    roomImpact.flush({ count: 0 });
    const roomRequest = http.expectOne(`/api/exam-rooms/${venue.rooms[0].id}`);
    expect(roomRequest.request.body.confirm_future_assignments).toBe(false);
    roomRequest.flush({ ...venue.rooms[0], name: 'A-102', revision: 2 });
    flushDashboardRequests(http);

    workflow.createVenue(create);
    http
      .expectOne('/api/exam-venues/duplicate-check')
      .flush({ error: 'unavailable' }, { status: 503, statusText: 'Unavailable' });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Dublettenprüfung fehlgeschlagen',
    );

    const confirm = TestBed.inject(TuiConfirmService);
    vi.spyOn(confirm, 'withConfirm').mockReturnValue(of(false));
    workflow.createVenue(create);
    http.expectOne('/api/exam-venues/duplicate-check').flush({
      items: [{ id: 9, name: 'Prüfungszentrum West', address: 'Testweg 2, Hamburg' }],
    });

    workflow.updateVenue(update);
    http.expectOne(`/api/exam-venues/${venue.id}/change-impact`).flush({
      count: 2,
      date_from: '2026-11-01',
      date_to: '2026-11-30',
    });
    http.expectOne('/api/exam-venues/duplicate-check').flush({ items: [] });
    expect(http.match(`/api/exam-venues/${venue.id}`)).toHaveLength(0);

    workflow.updateVenue(update);
    http.expectOne('/api/exam-venues/duplicate-check').flush({ items: [] });
    http
      .expectOne(`/api/exam-venues/${venue.id}/change-impact`)
      .flush({ error: 'unavailable' }, { status: 503, statusText: 'Unavailable' });
  });

  it('keeps explicit geocoding candidates separate from venue data on success and failure', () => {
    TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);
    const workflow = TestBed.inject(VenueWorkflowService) as unknown as {
      geocodeVenue(venue: ExamVenue): void;
      geocodeCandidate(): {
        venueId: number;
        latitude: number;
        longitude: number;
        source: string;
      } | null;
      updateVenue(update: VenueUpdate): void;
    };
    const workspace = TestBed.inject(ApplicationWorkspaceService);
    const venue = masterDataFixture.examVenues[0];

    workflow.geocodeVenue(venue);
    expect(workspace.actionBusy()).toBe(true);
    const success = http.expectOne(`/api/exam-venues/${venue.id}/geocode`);
    expect(success.request.body).toEqual({ expected_revision: venue.revision });
    success.flush({ latitude: 53.55, longitude: 9.99, source: 'nominatim' });
    expect(workflow.geocodeCandidate()).toEqual({
      venueId: venue.id,
      latitude: 53.55,
      longitude: 9.99,
      source: 'nominatim',
    });
    expect(workspace.actionBusy()).toBe(false);

    workflow.geocodeVenue(venue);
    http
      .expectOne(`/api/exam-venues/${venue.id}/geocode`)
      .flush({}, { status: 503, statusText: 'Provider unavailable' });
    expect(workflow.geocodeCandidate()).toEqual({
      venueId: venue.id,
      latitude: 53.55,
      longitude: 9.99,
      source: 'nominatim',
    });
    expect(workspace.actionBusy()).toBe(false);

    const coordinateUpdate: VenueUpdate = {
      id: venue.id,
      payload: {
        expected_revision: venue.revision,
        latitude: 53.55,
        longitude: 9.99,
        coordinate_status: 'confirmed',
        coordinate_source: 'nominatim',
      },
    };
    workflow.updateVenue(coordinateUpdate);
    http.expectOne(`/api/exam-venues/${venue.id}/change-impact`).flush({ count: 0 });
    http.expectOne('/api/exam-venues/duplicate-check').flush({ items: [] });
    http
      .expectOne(`/api/exam-venues/${venue.id}`)
      .flush({ ...venue, ...coordinateUpdate.payload, revision: venue.revision + 1 });
    flushDashboardRequests(http);
    expect(workflow.geocodeCandidate()).toBeNull();

    workflow.geocodeVenue(venue);
    http
      .expectOne(`/api/exam-venues/${venue.id}/geocode`)
      .flush({ latitude: 53.55, longitude: 9.99, source: 'nominatim' });
    workflow.updateVenue(coordinateUpdate);
    http.expectOne(`/api/exam-venues/${venue.id}/change-impact`).flush({ count: 0 });
    http.expectOne('/api/exam-venues/duplicate-check').flush({ items: [] });
    http
      .expectOne(`/api/exam-venues/${venue.id}`)
      .flush({}, { status: 503, statusText: 'Provider unavailable' });
    expect(workflow.geocodeCandidate()).not.toBeNull();
  });

  it('routes into and out of the selected venue detail', async () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    const router = TestBed.inject(Router);
    flushDashboardRequests(http);
    await router.navigateByUrl('/locations');
    await stabilizeRoute(fixture);
    const route = routeComponent(fixture, LocationsRouteComponent) as unknown as {
      openVenue(id: number): void;
      closeDetail(): void;
    };

    route.openVenue(masterDataFixture.examVenues[0].id);
    await fixture.whenStable();
    expect(router.url).toBe(`/locations/${masterDataFixture.examVenues[0].id}`);
    expect((fixture.componentInstance as unknown as { breadcrumb(): string }).breadcrumb()).toBe(
      'Globale Bereiche',
    );

    const detailRoute = routeComponent(fixture, LocationsRouteComponent) as unknown as {
      closeDetail(): void;
    };
    detailRoute.closeDetail();
    await fixture.whenStable();
    expect(router.url).toBe('/locations');
  });

  it('covers confirmed venue actions and their non-mutating failure paths', () => {
    TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);
    const confirm = TestBed.inject(TuiConfirmService);
    vi.spyOn(confirm, 'withConfirm').mockReturnValue(of(true));
    const workflow = TestBed.inject(VenueWorkflowService) as unknown as {
      requestVenueDeletion(venue: ExamVenue): void;
      createVenue(payload: VenueCreate): void;
      updateRoom(update: RoomUpdate): void;
    };
    const venue = masterDataFixture.examVenues[0];

    workflow.requestVenueDeletion(venue);
    http
      .expectOne(`/api/exam-venues/${venue.id}`)
      .flush({}, { status: 409, statusText: 'Venue in use' });

    const create: VenueCreate = {
      scope: 'committee',
      committee_id: 1,
      name: 'Prüfungszentrum West',
      street: 'Testweg 2',
      postal_code: '20095',
      city: 'Hamburg',
      country: 'Deutschland',
      accessibility_status: 'confirmed',
      is_accessible: true,
      is_active: true,
    };
    workflow.createVenue(create);
    http.expectOne('/api/exam-venues/duplicate-check').flush({ items: [] });
    http
      .expectOne('/api/exam-venues')
      .flush({}, { status: 503, statusText: 'Persistence unavailable' });

    const roomUpdate: RoomUpdate = {
      id: venue.rooms[0].id,
      payload: { expected_revision: venue.rooms[0].revision, name: 'A-102' },
    };
    workflow.updateRoom(roomUpdate);
    http.expectOne(`/api/exam-rooms/${roomUpdate.id}/change-impact`).flush({
      count: 1,
      date_from: '2026-11-01',
      date_to: '2026-11-01',
    });
    http
      .expectOne(`/api/exam-rooms/${roomUpdate.id}`)
      .flush({}, { status: 409, statusText: 'Revision conflict' });

    workflow.updateRoom(roomUpdate);
    http
      .expectOne(`/api/exam-rooms/${roomUpdate.id}/change-impact`)
      .flush({}, { status: 503, statusText: 'Impact unavailable' });
  });

  it('routes every nested venue command through the aggregate API', () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);
    const workflow = TestBed.inject(VenueWorkflowService) as unknown as {
      deleteVenue(venue: ExamVenue): void;
      createRoom(command: RoomCreate): void;
      deleteRoom(room: ExamRoom): void;
      createContact(command: ContactCreate): void;
      updateContact(command: ContactUpdate): void;
      deleteContact(contact: ExamVenueContact): void;
      requestPromotion(command: { venue: ExamVenue; reason: string }): void;
      decidePromotion(command: {
        venue: ExamVenue;
        decision: 'approve' | 'reject';
        reason: string;
      }): void;
    };
    const venue = masterDataFixture.examVenues[0];
    const room = venue.rooms[0];
    const contact: ExamVenueContact = {
      id: 4,
      venue_id: venue.id,
      label: 'Empfang',
      role: null,
      phone: '+49 40 123',
      email: null,
      availability_notes: null,
      is_active: 1,
      revision: 3,
      room_ids: [],
      _links: {},
    };
    const fail = (path: string, method: string) => {
      const request = http.expectOne(path);
      expect(request.request.method).toBe(method);
      request.flush({ error: 'expected test failure' }, { status: 409, statusText: 'Conflict' });
    };

    workflow.deleteVenue(venue);
    const deleteVenue = http.expectOne(`/api/exam-venues/${venue.id}`);
    expect(deleteVenue.request.method).toBe('DELETE');
    deleteVenue.flush(null, { status: 204, statusText: 'No Content' });
    flushDashboardRequests(http);
    workflow.createRoom({
      venueId: venue.id,
      payload: { name: 'B-202', capacity: 12, is_active: true },
    });
    fail(`/api/exam-venues/${venue.id}/rooms`, 'POST');
    workflow.deleteRoom(room);
    fail(`/api/exam-rooms/${room.id}`, 'DELETE');
    workflow.createContact({
      venueId: venue.id,
      payload: {
        label: 'Empfang',
        email: null,
        phone: '123',
        availability_notes: null,
        is_active: true,
      },
    });
    fail(`/api/exam-venues/${venue.id}/contacts`, 'POST');
    workflow.updateContact({
      id: contact.id,
      payload: { expected_revision: contact.revision, label: 'Neu' },
    });
    fail(`/api/exam-venue-contacts/${contact.id}`, 'PATCH');
    workflow.deleteContact(contact);
    fail(`/api/exam-venue-contacts/${contact.id}`, 'DELETE');
    workflow.requestPromotion({ venue, reason: 'Bundesweit geeignet' });
    fail(`/api/exam-venues/${venue.id}/promotion-requests`, 'POST');
    workflow.decidePromotion({ venue, decision: 'approve', reason: 'Geprüft' });
    fail(`/api/exam-venue-promotion-requests/${venue.id}/decision`, 'POST');

    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Aktion fehlgeschlagen');
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
