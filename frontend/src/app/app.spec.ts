import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';

import { App } from './app';
import {
  apiRootFixture,
  assignmentsFixture,
  availabilitiesFixture,
  candidateDaysFixture,
  committeesFixture,
  examDaysFixture,
  examSlotsFixture,
  locationsFixture,
  membersFixture,
  summaryFixture,
} from './testing/fixtures';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideHttpClient(), provideHttpClientTesting()],
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
});

function flushDashboardRequests(http: HttpTestingController): void {
  http.expectOne('/api').flush(apiRootFixture);
  http.expectOne('/api/round-summary?round_id=1').flush(summaryFixture);
  http.expectOne('/api/exam-days?round_id=1').flush({ items: examDaysFixture, _links: {} });
  http.expectOne('/api/exam-slots').flush({ items: examSlotsFixture, _links: {} });
  http.expectOne('/api/exam-day-assignments').flush({ items: assignmentsFixture, _links: {} });
  http.expectOne('/api/locations').flush({ items: locationsFixture, _links: {} });
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
}
