import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { provideRouter, Router } from '@angular/router';

import { App } from './app';
import { routes } from './app.routes';
import {
  apiRootFixture,
  assignmentsFixture,
  availabilitiesFixture,
  candidateDaysFixture,
  candidatesFixture,
  committeesFixture,
  examDaysFixture,
  examRoundFixture,
  examSlotsFixture,
  locationsFixture,
  membersFixture,
  roundCandidatesFixture,
  summaryFixture,
} from './testing/fixtures';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter(routes), provideHttpClient(), provideHttpClientTesting()],
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

  it('should ask before deleting a candidate', async () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    flushDashboardRequests(http);
    fixture.detectChanges();

    await TestBed.inject(Router).navigateByUrl('/candidates');
    fixture.detectChanges();
    clickButton(fixture, 'Löschen');
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Prüfling löschen?');
    expect(http.match((request) => request.method === 'DELETE').length).toBe(0);

    clickButton(fixture, 'Abbrechen');
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).not.toContain('Prüfling löschen?');
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

  const roundCandidateRequests = http.match('/api/round-candidates?round_id=1');
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

  http.expectOne('/api/committees').flush({
    items: committeesFixture,
    _links: {},
  });

  const locationRequests = http.match('/api/locations');
  expect(locationRequests.length).toBe(2);
  locationRequests.forEach((request) => request.flush({ items: locationsFixture, _links: {} }));
}
