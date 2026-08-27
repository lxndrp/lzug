import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';

import { AuthService } from '../auth/auth.service';
import { AbsenceReportsComponent } from './absence-reports.component';

describe('AbsenceReportsComponent', () => {
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AbsenceReportsComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTaiga({ scrollbars: 'native' }),
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 1,
      person_id: 7,
      committee_member_id: 7,
      is_operator: false,
    });
  });

  afterEach(() => http.verify());

  it('renders an own pending replacement response and audit history', () => {
    const fixture = TestBed.createComponent(AbsenceReportsComponent);
    fixture.detectChanges();
    http.expectOne('/api/absence-reports').flush({ items: [report()], _links: {} });
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Ausfallmeldung #1');
    expect(element.textContent).toContain('Ihre Ersatzanfrage');
    expect(element.textContent).toContain('Historie anzeigen (1)');
    expect(element.querySelectorAll('button')).toHaveLength(2);
  });

  it('persists an available answer and updates the report', () => {
    const fixture = TestBed.createComponent(AbsenceReportsComponent);
    fixture.detectChanges();
    http.expectOne('/api/absence-reports').flush({ items: [report()], _links: {} });
    fixture.detectChanges();

    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('button')?.click();
    const request = http.expectOne('/api/replacement-responses/5');
    expect(request.request.body).toEqual({ response: 'available' });
    request.flush(report({ response: 'available' }));
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Ersatzantwort gespeichert.',
    );
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('available');
  });

  it('reports answer and loading failures to the user', () => {
    const fixture = TestBed.createComponent(AbsenceReportsComponent);
    fixture.detectChanges();
    http.expectOne('/api/absence-reports').flush({ items: [report()], _links: {} });
    fixture.detectChanges();
    (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button')[1].click();
    http
      .expectOne('/api/replacement-responses/5')
      .flush({ error: 'failed' }, { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Ersatzantwort konnte nicht gespeichert werden.',
    );

    const failedFixture = TestBed.createComponent(AbsenceReportsComponent);
    failedFixture.detectChanges();
    http
      .expectOne('/api/absence-reports')
      .flush({ error: 'failed' }, { status: 500, statusText: 'Server Error' });
    failedFixture.detectChanges();
    expect((failedFixture.nativeElement as HTMLElement).textContent).toContain(
      'Ausfallprozesse konnten nicht geladen werden.',
    );
  });
});

function report(overrides: { response?: 'available' | 'pending' } = {}) {
  return {
    id: 1,
    exam_day_id: 7,
    exam_day_assignment_id: 8,
    committee_member_id: 3,
    reported_by_member_id: 3,
    reported_at: '2026-11-01T09:00:00+00:00',
    reason: null,
    status: 'replacement_requested',
    selected_replacement_member_id: null,
    version: 1,
    created_at: '2026-11-01T09:00:00+00:00',
    updated_at: '2026-11-01T09:00:00+00:00',
    responses: [
      {
        id: 5,
        committee_member_id: 7,
        response: overrides.response ?? 'pending',
        requested_at: '2026-11-01T09:00:00+00:00',
        expires_at: null,
        urgent: true,
        responded_at: null,
      },
    ],
    audit: [
      {
        id: 1,
        actor_member_id: 3,
        event_type: 'reported',
        from_status: null,
        to_status: 'replacement_requested',
        details: null,
        created_at: '2026-11-01T09:00:00+00:00',
      },
    ],
  };
}
