import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { AuthService } from '../auth/auth.service';
import { PERSONAL_PORT, type PersonalPort } from '../personal/personal.port';
import { AbsenceReportsComponent } from './absence-reports.component';

describe('AbsenceReportsComponent', () => {
  let personal: PersonalPort;

  beforeEach(async () => {
    personal = createPersonalPort();
    await TestBed.configureTestingModule({
      imports: [AbsenceReportsComponent],
      providers: [
        provideRouter([]),
        { provide: PERSONAL_PORT, useValue: personal },
        provideTaiga({ scrollbars: 'native' }),
      ],
    }).compileComponents();
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 1,
      person_id: 7,
      committee_member_id: 7,
      is_operator: false,
    });
  });

  it('renders an own pending replacement response and audit history', () => {
    personal.listAbsenceReports = vi.fn().mockReturnValue(of([report()]));
    const fixture = TestBed.createComponent(AbsenceReportsComponent);
    fixture.detectChanges();
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
    personal.listAbsenceReports = vi.fn().mockReturnValue(of([report()]));
    const fixture = TestBed.createComponent(AbsenceReportsComponent);
    fixture.detectChanges();
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('für diese Demo-Rolle read-only');
    expect(element.querySelectorAll('button')).toHaveLength(0);
  });

  it('persists an available answer and updates the report', () => {
    personal.listAbsenceReports = vi.fn().mockReturnValue(of([report()]));
    personal.answerReplacement = vi.fn().mockReturnValue(of(report({ response: 'available' })));
    const fixture = TestBed.createComponent(AbsenceReportsComponent);
    fixture.detectChanges();
    fixture.detectChanges();

    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('button')?.click();
    expect(personal.answerReplacement).toHaveBeenCalledWith(5, 'available');
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
    personal.listAbsenceReports = vi.fn().mockReturnValue(of([report()]));
    personal.answerReplacement = vi.fn().mockReturnValue(of(report({ response: 'available' })));
    const fixture = TestBed.createComponent(AbsenceReportsComponent);
    fixture.detectChanges();
    fixture.detectChanges();

    const buttons = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    );
    expect(buttons.map((button) => button.textContent?.trim())).toEqual(['Ich kann übernehmen']);
    expect((fixture.nativeElement as HTMLElement).textContent).not.toContain(
      'Ich kann nicht übernehmen',
    );

    buttons[0].click();
    expect(personal.answerReplacement).toHaveBeenCalledWith(5, 'available');
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
    personal.listAbsenceReports = vi.fn().mockReturnValue(of([report({ response: 'available' })]));
    personal.selectReplacement = vi
      .fn()
      .mockReturnValue(of(report({ response: 'available', selected: true })));
    const fixture = TestBed.createComponent(AbsenceReportsComponent);
    fixture.detectChanges();
    fixture.detectChanges();

    const button = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      'button',
    );
    expect(button?.textContent).toContain('Vorgegebenen Ersatz auswählen');
    button?.click();
    expect(personal.selectReplacement).toHaveBeenCalledWith(1, 7, 1);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Ersatz ausgewählt.');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Öffnen Sie die Demo-Szenarien',
    );
  });

  it('reports answer and loading failures to the user', () => {
    personal.listAbsenceReports = vi.fn().mockReturnValue(of([report()]));
    personal.answerReplacement = vi.fn().mockReturnValue(throwError(() => new Error()));
    const fixture = TestBed.createComponent(AbsenceReportsComponent);
    fixture.detectChanges();
    fixture.detectChanges();
    (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button')[1].click();
    expect(personal.answerReplacement).toHaveBeenCalledWith(5, 'unavailable');
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Ersatzantwort konnte nicht gespeichert werden.',
    );

    const failedFixture = TestBed.createComponent(AbsenceReportsComponent);
    personal.listAbsenceReports = vi.fn().mockReturnValue(throwError(() => new Error()));
    failedFixture.detectChanges();
    failedFixture.detectChanges();
    expect((failedFixture.nativeElement as HTMLElement).textContent).toContain(
      'Ausfallprozesse konnten nicht geladen werden.',
    );
  });
});

function report(overrides: { response?: 'available' | 'pending'; selected?: boolean } = {}) {
  return {
    id: 1,
    examDayId: 7,
    examDayAssignmentId: 8,
    committeeMemberId: 3,
    reportedByMemberId: 3,
    reportedAt: '2026-11-01T09:00:00+00:00',
    reason: null,
    status: overrides.selected ? 'replacement_selected' : 'replacement_requested',
    selectedReplacementMemberId: overrides.selected ? 7 : null,
    version: 1,
    createdAt: '2026-11-01T09:00:00+00:00',
    updatedAt: '2026-11-01T09:00:00+00:00',
    responses: [
      {
        id: 5,
        committeeMemberId: 7,
        response: overrides.response ?? 'pending',
        requestedAt: '2026-11-01T09:00:00+00:00',
        expiresAt: null,
        urgent: true,
        respondedAt: null,
      },
    ],
    audit: [
      {
        id: 1,
        actorMemberId: 3,
        eventType: 'reported',
        fromStatus: null,
        toStatus: 'replacement_requested',
        details: null,
        createdAt: '2026-11-01T09:00:00+00:00',
      },
    ],
  };
}

function createPersonalPort(): PersonalPort {
  return {
    listNotifications: vi.fn().mockReturnValue(of([])),
    listNotificationProblems: vi.fn().mockReturnValue(of([])),
    listNotificationOverview: vi.fn().mockReturnValue(of([])),
    getNotificationChannels: vi.fn().mockReturnValue(
      of({
        webPush: { available: false, publicKey: null },
        emailFallbackConfigured: false,
        sinkEnabled: false,
      }),
    ),
    getCalendarStatus: vi
      .fn()
      .mockReturnValue(
        of({ active: false, activatedAt: null, revokedAt: null, timeZone: 'Europe/Berlin' }),
      ),
    listCalendarEvents: vi.fn().mockReturnValue(of([])),
    downloadCalendarEvent: vi
      .fn()
      .mockReturnValue(
        of({ content: 'BEGIN:VCALENDAR', mediaType: 'text/calendar', fileName: 'calendar.ics' }),
      ),
    activateCalendarFeed: vi.fn().mockReturnValue(
      of({
        active: true,
        activatedAt: null,
        revokedAt: null,
        timeZone: 'Europe/Berlin',
        feedUrl: '/api/calendar/feed/test.ics',
        notice: 'activated',
      }),
    ),
    revokeCalendarFeed: vi.fn().mockReturnValue(
      of({
        active: false,
        activatedAt: null,
        revokedAt: null,
        timeZone: 'Europe/Berlin',
        notice: 'revoked',
      }),
    ),
    listAbsenceReports: vi.fn().mockReturnValue(of([])),
    createAbsenceReport: vi.fn().mockReturnValue(of(report())),
    answerReplacement: vi.fn().mockReturnValue(of(report())),
    selectReplacement: vi.fn().mockReturnValue(of(report())),
    registerPushSubscription: vi.fn().mockReturnValue(of(undefined)),
  };
}
