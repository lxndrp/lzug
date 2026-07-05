import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';

import { App } from './app';

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

    http.expectOne('/api').flush({
      name: 'lzug API',
      _links: {},
    });
    http.expectOne('/api/round-summary?round_id=1').flush({
      round: {
        id: 1,
        name: 'Winter 2026/27',
        status: 'availability_requested',
        committee_name: 'PA Fachinformatiker Hamburg 1',
      },
      counts: {
        candidates: 12,
        mep_count: 4,
        required_exam_slots: 16,
      },
      settings: {
        calendar_week_from: '2026-W47',
        calendar_week_to: '2026-W49',
        exams_per_day: 6,
        max_exam_days_per_week: 3,
      },
      availability: [{ availability: 'pending', count: 10 }],
      _links: {},
    });
    http.expectOne('/api/exam-days?round_id=1').flush({ items: [], _links: {} });
    http.expectOne('/api/exam-slots').flush({ items: [], _links: {} });
    http.expectOne('/api/exam-day-assignments').flush({ items: [], _links: {} });
    http.expectOne('/api/members').flush({ items: [], _links: {} });
    http.expectOne('/api/locations').flush({ items: [], _links: {} });
    http.expectOne('/api/candidate-exam-days?round_id=1').flush({ items: [], _links: {} });
    http.expectOne('/api/member-availabilities?round_id=1').flush({ items: [], _links: {} });
    http.expectOne('/api/committees').flush({
      items: [{ id: 1, name: 'PA Fachinformatiker Hamburg 1', occupation: 'Fachinformatiker/in' }],
      _links: {},
    });

    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('h1')?.textContent).toContain('Winter 2026/27');
    expect(compiled.textContent).toContain('Planung erzeugen');
  });
});
