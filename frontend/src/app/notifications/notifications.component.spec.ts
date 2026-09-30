import { TestBed } from '@angular/core/testing';
import { provideTaiga } from '@taiga-ui/core';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { AuthService } from '../auth/auth.service';
import { PERSONAL_PORT, type PersonalPort } from '../personal/personal.port';
import { NotificationsComponent } from './notifications.component';

describe('NotificationsComponent', () => {
  let personal: PersonalPort;

  beforeEach(async () => {
    personal = createPersonalPort();
    await TestBed.configureTestingModule({
      imports: [NotificationsComponent],
      providers: [
        { provide: PERSONAL_PORT, useValue: personal },
        provideRouter([]),
        provideTaiga({ scrollbars: 'native' }),
      ],
    }).compileComponents();
  });

  it('renders own content and only technical metadata for committee problems', () => {
    personal.listNotifications = vi.fn().mockReturnValue(
      of([
        {
          id: 1,
          eventType: 'availability_reminder',
          title: 'Verfügbarkeitsrückmeldung offen',
          message: 'Ihre Rückmeldung ist noch offen.',
          actionPath: '/scheduling-overview/1',
          createdAt: '2026-09-29T18:00:00+00:00',
        },
      ]),
    );
    personal.listNotificationOverview = vi.fn().mockReturnValue(
      of([
        {
          notificationId: 2,
          eventType: 'availability_requested',
          recipientMemberId: 7,
          channel: 'web_push',
          status: 'unavailable',
          attemptCount: 0,
          errorCode: 'not_registered',
          updatedAt: '2026-09-29T18:00:00+00:00',
        },
      ]),
    );
    const fixture = TestBed.createComponent(NotificationsComponent);
    fixture.detectChanges();

    const content = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(content).toContain('Verfügbarkeitsrückmeldung offen');
    expect(content).toContain('Ihre Rückmeldung ist noch offen.');
    expect(content).toContain('Zustellstatus im Ausschuss');
    expect(content).toContain('Nicht verfügbar');
    expect(content).not.toContain('Inhalt eines anderen Mitglieds');
    expect(personal.listNotifications).toHaveBeenCalledOnce();
    expect(personal.listNotificationOverview).toHaveBeenCalledOnce();
  });

  it('keeps push and feed management read-only without demo mutation capabilities', () => {
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 2,
      person_id: 3,
      committee_member_id: 3,
      is_operator: false,
      demo_role: 'examiner',
      capabilities: ['notifications:read-own', 'calendar:read-own'],
    });
    personal.getNotificationChannels = vi.fn().mockReturnValue(
      of({
        webPush: { available: true, publicKey: 'test-key' },
        emailFallbackConfigured: false,
        sinkEnabled: false,
      }),
    );
    personal.listCalendarEvents = vi.fn().mockReturnValue(
      of([
        {
          id: 1,
          externalEventId: 'calendar-event-1',
          date: '2026-11-16',
          startsAt: '08:30',
          endsAt: '09:30',
          timeZone: 'Europe/Berlin',
          location: 'Raum 1',
          role: 'Prüfperson',
          roundName: 'Winterprüfung 2026',
          status: 'sent',
          version: 1,
        },
      ]),
    );
    const fixture = TestBed.createComponent(NotificationsComponent);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain(
      'Externe Zustellung ist in der öffentlichen Demo deaktiviert.',
    );
    expect(element.textContent).toContain('Feed-Aktivierung, Neuerzeugung und Widerruf');
    expect(element.textContent).not.toContain('Browser-Benachrichtigungen aktivieren');
    expect(element.textContent).not.toContain('Persönlichen Feed aktivieren');
    expect(
      Array.from(element.querySelectorAll('button')).some((button) =>
        button.textContent?.includes('Datei laden'),
      ),
    ).toBe(true);
  });

  it('downloads a calendar event through the personal port', async () => {
    personal.downloadCalendarEvent = vi.fn().mockReturnValue(
      of({
        content: 'BEGIN:VCALENDAR',
        mediaType: 'text/calendar; charset=utf-8',
        fileName: 'winterpruefung.ics',
      }),
    );
    const fixture = TestBed.createComponent(NotificationsComponent);
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:calendar');
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    (
      fixture.componentInstance as unknown as { downloadCalendarEvent(id: number): void }
    ).downloadCalendarEvent(5);

    expect(personal.downloadCalendarEvent).toHaveBeenCalledWith(5);
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(click).toHaveBeenCalledOnce();
    await new Promise((resolve) => window.setTimeout(resolve, 1));
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:calendar');
  });

  it('shows calendar download failures in the calendar status area', () => {
    personal.downloadCalendarEvent = vi.fn().mockReturnValue(throwError(() => new Error()));
    const fixture = TestBed.createComponent(NotificationsComponent);
    fixture.detectChanges();

    (
      fixture.componentInstance as unknown as { downloadCalendarEvent(id: number): void }
    ).downloadCalendarEvent(5);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain(
      'Der Kalendereintrag konnte nicht heruntergeladen werden.',
    );
    expect(element.querySelector('[role="status"]')?.textContent).toContain(
      'Der Kalendereintrag konnte nicht heruntergeladen werden.',
    );
    expect(element.textContent).not.toContain(
      'Browser-Benachrichtigungen konnten nicht aktiviert werden.',
    );
  });

  it('explains a denied browser permission without registering an endpoint', async () => {
    const fixture = TestBed.createComponent(NotificationsComponent);
    const component = fixture.componentInstance as unknown as {
      channels: { set(value: unknown): void };
      canEnablePush(): boolean;
      enablePush(): Promise<void>;
      pushMessage(): string | null;
    };
    component.channels.set({
      webPush: { available: true, publicKey: 'test-key' },
      emailFallbackConfigured: false,
      sinkEnabled: false,
    });
    component.canEnablePush = () => true;
    const originalNotification = globalThis.Notification;
    Object.defineProperty(globalThis, 'Notification', {
      configurable: true,
      value: { requestPermission: vi.fn().mockResolvedValue('denied') },
    });

    try {
      await component.enablePush();
    } finally {
      Object.defineProperty(globalThis, 'Notification', {
        configurable: true,
        value: originalNotification,
      });
    }

    expect(component.pushMessage()).toBe('Browser-Benachrichtigungen wurden nicht erlaubt.');
    expect(personal.registerPushSubscription).not.toHaveBeenCalled();
  });

  it('activates, rotates, and revokes the personal calendar feed', () => {
    const fixture = TestBed.createComponent(NotificationsComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance as unknown as {
      activateCalendar(rotate?: boolean): void;
      revokeCalendar(): void;
      feedUrl(): string | null;
      calendarMessage(): string | null;
      calendarStatusLabel(event: never): string;
      calendarBusy: { set(value: boolean): void };
    };
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);

    try {
      component.calendarBusy.set(true);
      component.activateCalendar();
      component.revokeCalendar();
      expect(personal.activateCalendarFeed).not.toHaveBeenCalled();
      expect(personal.revokeCalendarFeed).not.toHaveBeenCalled();
      component.calendarBusy.set(false);

      personal.activateCalendarFeed = vi.fn().mockReturnValue(
        of({
          active: true,
          activatedAt: '2026-10-01T10:00:00+00:00',
          revokedAt: null,
          timeZone: 'Europe/Berlin',
          feedUrl: '/api/calendar/feed/first.ics',
          notice: 'first activation',
        }),
      );
      component.activateCalendar();
      expect(personal.activateCalendarFeed).toHaveBeenCalledWith(false);
      expect(component.feedUrl()).toBe('/api/calendar/feed/first.ics');
      expect(component.calendarMessage()).toBe('first activation');

      personal.activateCalendarFeed = vi.fn().mockReturnValue(
        of({
          active: true,
          activatedAt: '2026-10-01T11:00:00+00:00',
          revokedAt: null,
          timeZone: 'Europe/Berlin',
          feedUrl: '/api/calendar/feed/second.ics',
          notice: 'rotated',
        }),
      );
      component.activateCalendar(true);
      expect(personal.activateCalendarFeed).toHaveBeenCalledWith(true);
      expect(component.feedUrl()).toBe('/api/calendar/feed/second.ics');

      personal.revokeCalendarFeed = vi.fn().mockReturnValue(
        of({
          active: false,
          activatedAt: '2026-10-01T11:00:00+00:00',
          revokedAt: '2026-10-01T12:00:00+00:00',
          timeZone: 'Europe/Berlin',
          notice: 'revoked',
        }),
      );
      component.revokeCalendar();
      expect(personal.revokeCalendarFeed).toHaveBeenCalledOnce();
      expect(component.feedUrl()).toBeNull();
      expect(component.calendarMessage()).toBe('revoked');
      expect(component.calendarStatusLabel({ status: 'cancelled' } as never)).toBe('Storniert');
      expect(component.calendarStatusLabel({ status: 'updated' } as never)).toBe('Geändert');
      expect(component.calendarStatusLabel({ status: 'sent' } as never)).toBe('Bestätigt');
    } finally {
      confirm.mockRestore();
    }
  });

  it('reports feed errors and honors activation and revoke cancellations', () => {
    const fixture = TestBed.createComponent(NotificationsComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance as unknown as {
      activateCalendar(rotate?: boolean): void;
      revokeCalendar(): void;
      calendarMessage(): string | null;
    };
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);

    try {
      component.activateCalendar(true);
      expect(personal.activateCalendarFeed).not.toHaveBeenCalled();
      component.revokeCalendar();
      expect(personal.revokeCalendarFeed).not.toHaveBeenCalled();

      confirm.mockReturnValue(true);
      personal.activateCalendarFeed = vi.fn().mockReturnValue(throwError(() => new Error()));
      component.activateCalendar();
      expect(component.calendarMessage()).toBe(
        'Der persönliche Kalenderzugang konnte nicht aktiviert werden.',
      );

      personal.revokeCalendarFeed = vi.fn().mockReturnValue(throwError(() => new Error()));
      component.revokeCalendar();
      expect(component.calendarMessage()).toBe(
        'Der persönliche Kalenderzugang konnte nicht widerrufen werden.',
      );
    } finally {
      confirm.mockRestore();
    }
  });

  it('reports initial calendar loading errors', () => {
    personal.getCalendarStatus = vi.fn().mockReturnValue(throwError(() => new Error()));
    const fixture = TestBed.createComponent(NotificationsComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      pushMessage(): string | null;
    };
    expect(component.pushMessage()).toBe('Benachrichtigungen konnten nicht geladen werden.');
  });
});

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
    createAbsenceReport: vi.fn().mockReturnValue(of(emptyReport())),
    answerReplacement: vi.fn().mockReturnValue(of(emptyReport())),
    selectReplacement: vi.fn().mockReturnValue(of(emptyReport())),
    registerPushSubscription: vi.fn().mockReturnValue(of(undefined)),
  };
}

function emptyReport() {
  return {
    id: 1,
    examDayId: 1,
    examDayAssignmentId: 1,
    committeeMemberId: 1,
    reportedByMemberId: 1,
    reportedAt: '',
    reason: null,
    status: '',
    selectedReplacementMemberId: null,
    version: 1,
    createdAt: '',
    updatedAt: '',
    responses: [],
    audit: [],
  };
}
