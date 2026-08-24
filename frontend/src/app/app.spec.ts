import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { provideRouter, Router } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';
import { TuiConfirmService } from '@taiga-ui/kit';
import { of } from 'rxjs';

import { App } from './app';
import { AuthService } from './auth/auth.service';
import { RoundContextService } from './api/round-context.service';
import { routes } from './app.routes';
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
  locationsFixture,
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
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter(routes),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTaiga({ scrollbars: 'native' }),
        TuiConfirmService,
        {
          provide: AuthService,
          useValue: {
            state: signal('authenticated'),
            initialize: () => of(true),
            markAnonymous: vi.fn(),
          },
        },
      ],
    }).compileComponents();
  });

  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
  });

  it('should render the exam round dashboard', () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);

    flushDashboardRequests(http);

    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('h1')?.textContent).toContain('Übersicht');
    expect(compiled.textContent).toContain('Terminorganisationen öffnen');
    expect(compiled.textContent).toContain('Aktueller Prüfungskontext');
    expect(compiled.textContent).toContain('Winter 2026');
    expect(compiled.textContent).toContain('Prüfungsausschuss Teststadt 1');
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
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);

    const app = fixture.componentInstance as unknown as {
      selectCommittee(id: number | null): void;
      selectedCommitteeId: () => number | null;
    };
    app.selectCommittee(2);

    expect(app.selectedCommitteeId()).toBe(2);
  });

  it('should refresh the visible context after selecting another exam round', () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);

    const app = fixture.componentInstance as unknown as {
      selectExamRound(id: number): void;
    };
    app.selectExamRound(2);
    flushDashboardRequests(http, examRoundsFixture[1]);
    fixture.detectChanges();

    expect(TestBed.inject(RoundContextService).roundId()).toBe(2);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Prüfungsausschuss Teststadt 2',
    );
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
        label: 'Prüfling Alpha löschen?',
        data: expect.objectContaining({ yes: 'Prüfling Alpha löschen' }),
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

  it('should expose operation errors as a consistent alert', () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);

    const app = fixture.componentInstance as unknown as {
      notify: (type: 'success' | 'error', title: string, message: string) => void;
      dismissFeedback: () => void;
    };
    app.notify('error', 'Nicht gespeichert', 'Bitte Eingaben prüfen.');
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
});

function clickButton(fixture: ComponentFixture<App>, label: string): void {
  const button = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('button')).find(
    (item) => item.textContent?.includes(label),
  );
  expect(button).toBeDefined();
  button?.click();
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

  const locationRequests = http.match('/api/locations');
  expect(locationRequests.length).toBe(2);
  locationRequests.forEach((request) => request.flush({ items: locationsFixture, _links: {} }));
}
