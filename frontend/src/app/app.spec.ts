import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { provideRouter, Router } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';
import { TuiConfirmService } from '@taiga-ui/kit';
import { of } from 'rxjs';

import { App } from './app';
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
    expect(compiled.querySelector('h1')?.textContent).toContain('Winter 2026/27');
    expect(compiled.textContent).toContain('Planung erzeugen');
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

    app.sidebarVisible.set(true);
    fixture.detectChanges();

    expect(toggle()?.getAttribute('aria-expanded')).toBe('true');
    expect(toggle()?.getAttribute('aria-label')).toBe('Navigation schließen');

    app.sidebarVisible.set(false);
    fixture.detectChanges();

    expect(toggle()?.getAttribute('aria-expanded')).toBe('false');
    expect(toggle()?.getAttribute('aria-label')).toBe('Navigation öffnen');
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
        label: 'Prüfling löschen?',
        data: expect.objectContaining({ yes: 'Prüfling löschen' }),
      }),
    );
    expect(http.match((request) => request.method === 'DELETE').length).toBe(0);
  });

  it('should use English URLs for frontend views', async () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    const router = TestBed.inject(Router);
    flushDashboardRequests(http);

    await router.navigateByUrl('/planning');
    fixture.detectChanges();

    expect(router.url).toBe('/planning');
    expect((fixture.nativeElement as HTMLElement).querySelector('h1')?.textContent).toContain(
      'Terminplanung',
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
    expect(element.querySelector('h1')?.textContent).toContain('Winter 2026/27');
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

function flushDashboardRequests(http: HttpTestingController): void {
  http.expectOne('/api').flush(apiRootFixture);
  http.expectOne('/api/exam-rounds/1').flush(examRoundFixture);
  http.expectOne('/api/round-summary?round_id=1').flush(summaryFixture);
  http.expectOne('/api/exam-days?round_id=1').flush({ items: examDaysFixture, _links: {} });
  http.expectOne('/api/exam-slots').flush({ items: examSlotsFixture, _links: {} });
  http.expectOne('/api/exam-day-assignments').flush({ items: assignmentsFixture, _links: {} });
  const candidateRequests = http.match('/api/candidates');
  expect(candidateRequests.length).toBe(2);
  candidateRequests.forEach((request) => request.flush({ items: candidatesFixture, _links: {} }));

  const roundCandidateRequests = http.match('/api/round-candidates?round_id=1&is_active=1');
  expect(roundCandidateRequests.length).toBe(2);
  roundCandidateRequests.forEach((request) =>
    request.flush({ items: roundCandidatesFixture, _links: {} }),
  );
  http.expectOne('/api/candidate-exam-days?round_id=1').flush({
    items: candidateDaysFixture,
    _links: {},
  });
  http.expectOne('/api/member-availabilities?round_id=1').flush({
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
  http.expectOne('/api/exam-rounds').flush({ items: examRoundsFixture, _links: {} });
  http.expectOne('/api/candidate-committee-assignments').flush({
    items: candidateAssignmentsFixture,
    _links: {},
  });

  const locationRequests = http.match('/api/locations');
  expect(locationRequests.length).toBe(2);
  locationRequests.forEach((request) => request.flush({ items: locationsFixture, _links: {} }));
}
