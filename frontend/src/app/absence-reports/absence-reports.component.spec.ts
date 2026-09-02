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

  it('keeps pending replacement responses read-only without the demo capability', () => {
    TestBed.inject(AuthService).session.update((session) => ({
      ...session!,
      demo_role: 'examiner',
      capabilities: ['absence:read-own'],
    }));
    const fixture = TestBed.createComponent(AbsenceReportsComponent);
    fixture.detectChanges();
    http.expectOne('/api/absence-reports').flush({ items: [report()], _links: {} });
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('für diese Demo-Rolle read-only');
    expect(element.querySelectorAll('button')).toHaveLength(0);
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

  it('limits the replacement demo role to its available answer', () => {
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 4,
      person_id: 6,
      committee_member_id: 7,
      is_operator: false,
      demo_role: 'replacement',
      capabilities: ['absence:respond-own'],
    });
    const fixture = TestBed.createComponent(AbsenceReportsComponent);
    fixture.detectChanges();
    http.expectOne('/api/absence-reports').flush({ items: [report()], _links: {} });
    fixture.detectChanges();

    const buttons = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    );
    expect(buttons.map((button) => button.textContent?.trim())).toEqual(['Ich kann übernehmen']);
    expect((fixture.nativeElement as HTMLElement).textContent).not.toContain(
      'Ich kann nicht übernehmen',
    );

    buttons[0].click();
    http.expectOne('/api/replacement-responses/5').flush(report({ response: 'available' }));
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Öffnen Sie die Demo-Szenarien für den nächsten Schritt.',
    );
  });

  it('lets the chair select only an available listed replacement', () => {
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 1,
      person_id: 1,
      committee_member_id: 1,
      is_operator: false,
      demo_role: 'chair',
      capabilities: ['absence:coordinate'],
    });
    const fixture = TestBed.createComponent(AbsenceReportsComponent);
    fixture.detectChanges();
    http.expectOne('/api/absence-reports').flush({
      items: [report({ response: 'available' })],
      _links: {},
    });
    fixture.detectChanges();

    const button = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      'button',
    );
    expect(button?.textContent).toContain('Vorgegebenen Ersatz auswählen');
    button?.click();
    const request = http.expectOne('/api/absence-reports/1/select-replacement');
    expect(request.request.body).toEqual({ committee_member_id: 7, version: 1 });
    request.flush({
      ...report({ response: 'available' }),
      status: 'replacement_selected',
      selected_replacement_member_id: 7,
      version: 2,
    });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Ersatz ausgewählt.');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Öffnen Sie die Demo-Szenarien',
    );
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
