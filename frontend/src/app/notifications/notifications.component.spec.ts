import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideTaiga } from '@taiga-ui/core';
import { vi } from 'vitest';

import { NotificationsComponent } from './notifications.component';

describe('NotificationsComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NotificationsComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTaiga({ scrollbars: 'native' }),
      ],
    }).compileComponents();
  });

  afterEach(() => TestBed.inject(HttpTestingController).verify({ ignoreCancelled: true }));

  it('renders own content and only technical metadata for committee problems', () => {
    const fixture = TestBed.createComponent(NotificationsComponent);
    const http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();

    http.expectOne('/api/notifications').flush({
      items: [
        {
          id: 1,
          event_type: 'availability_reminder',
          title: 'Verfügbarkeitsrückmeldung offen',
          message: 'Ihre Rückmeldung ist noch offen.',
          action_path: '/scheduling-overview/1',
          created_at: '2026-09-29T18:00:00+00:00',
        },
      ],
      _links: {},
    });
    http.expectOne('/api/notification-overview').flush({
      items: [
        {
          notification_id: 2,
          event_type: 'availability_requested',
          recipient_member_id: 7,
          channel: 'web_push',
          status: 'unavailable',
          attempt_count: 0,
          error_code: 'not_registered',
          updated_at: '2026-09-29T18:00:00+00:00',
        },
      ],
      _links: {},
    });
    http.expectOne('/api/notification-channels').flush({
      web_push: { available: false, public_key: null },
      email_fallback_configured: false,
      sink_enabled: false,
    });
    http.expectOne('/api/calendar').flush({
      active: false,
      activated_at: null,
      revoked_at: null,
      time_zone: 'Europe/Berlin',
      _links: {},
    });
    http.expectOne('/api/calendar/events').flush({ items: [], _links: {} });
    fixture.detectChanges();

    const content = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(content).toContain('Verfügbarkeitsrückmeldung offen');
    expect(content).toContain('Ihre Rückmeldung ist noch offen.');
    expect(content).toContain('Zustellstatus im Ausschuss');
    expect(content).toContain('Nicht verfügbar');
    expect(content).not.toContain('Inhalt eines anderen Mitglieds');
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
      web_push: { available: true, public_key: 'test-key' },
      email_fallback_configured: false,
      sink_enabled: false,
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
  });

  it('activates, rotates, and revokes the personal calendar feed', () => {
    const fixture = TestBed.createComponent(NotificationsComponent);
    const http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    flushInitialRequests(http, [
      {
        id: 1,
        external_event_id: 'calendar-event-1',
        date: '2026-11-16',
        starts_at: '08:30',
        ends_at: '09:30',
        time_zone: 'Europe/Berlin',
        location: 'Raum 1',
        role: 'Prüfperson',
        round_name: 'Winterprüfung 2026',
        status: 'sent',
        version: 1,
        download_url: '/api/calendar/events/1.ics',
      },
    ]);
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
      http.expectNone('/api/calendar/feed');
      component.calendarBusy.set(false);

      component.activateCalendar();
      const activation = http.expectOne('/api/calendar/feed');
      expect(activation.request.body).toEqual({ rotate: false });
      activation.flush({
        active: true,
        activated_at: '2026-10-01T10:00:00+00:00',
        revoked_at: null,
        time_zone: 'Europe/Berlin',
        feed_url: '/api/calendar/feed/first.ics',
        notice: 'first activation',
        _links: {},
      });
      expect(component.feedUrl()).toBe('/api/calendar/feed/first.ics');
      expect(component.calendarMessage()).toBe('first activation');
      fixture.detectChanges();
      expect((fixture.nativeElement as HTMLElement).textContent).toContain('Winterprüfung 2026');

      component.activateCalendar(true);
      const rotation = http.expectOne('/api/calendar/feed');
      expect(rotation.request.body).toEqual({ rotate: true });
      rotation.flush({
        active: true,
        activated_at: '2026-10-01T11:00:00+00:00',
        revoked_at: null,
        time_zone: 'Europe/Berlin',
        feed_url: '/api/calendar/feed/second.ics',
        notice: 'rotated',
        _links: {},
      });
      expect(component.feedUrl()).toBe('/api/calendar/feed/second.ics');

      component.revokeCalendar();
      const revoke = http.expectOne('/api/calendar/feed');
      expect(revoke.request.method).toBe('DELETE');
      revoke.flush({
        active: false,
        activated_at: '2026-10-01T11:00:00+00:00',
        revoked_at: '2026-10-01T12:00:00+00:00',
        time_zone: 'Europe/Berlin',
        notice: 'revoked',
        _links: {},
      });
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
    const http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    flushInitialRequests(http);

    const component = fixture.componentInstance as unknown as {
      activateCalendar(rotate?: boolean): void;
      revokeCalendar(): void;
      calendarMessage(): string | null;
    };
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);

    try {
      component.activateCalendar(true);
      http.expectNone('/api/calendar/feed');
      component.revokeCalendar();
      http.expectNone('/api/calendar/feed');

      component.activateCalendar();
      const activation = http.expectOne('/api/calendar/feed');
      activation.flush({ error: 'failed' }, { status: 500, statusText: 'Server Error' });
      expect(component.calendarMessage()).toBe(
        'Der persönliche Kalenderzugang konnte nicht aktiviert werden.',
      );

      confirm.mockReturnValue(true);
      component.revokeCalendar();
      const revoke = http.expectOne('/api/calendar/feed');
      revoke.flush({ error: 'failed' }, { status: 500, statusText: 'Server Error' });
      expect(component.calendarMessage()).toBe(
        'Der persönliche Kalenderzugang konnte nicht widerrufen werden.',
      );
    } finally {
      confirm.mockRestore();
    }
  });

  it('reports initial calendar loading errors', () => {
    const fixture = TestBed.createComponent(NotificationsComponent);
    const http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();

    http.expectOne('/api/notifications').flush({ items: [], _links: {} });
    http.expectOne('/api/notification-overview').flush({ items: [], _links: {} });
    http.expectOne('/api/notification-channels').flush({
      web_push: { available: false, public_key: null },
      email_fallback_configured: false,
      sink_enabled: false,
    });
    http.expectOne('/api/calendar').flush({}, { status: 500, statusText: 'Server Error' });

    const component = fixture.componentInstance as unknown as {
      pushMessage(): string | null;
    };
    expect(component.pushMessage()).toBe('Benachrichtigungen konnten nicht geladen werden.');
  });
});

function flushInitialRequests(http: HttpTestingController, events: unknown[] = []): void {
  http.expectOne('/api/notifications').flush({ items: [], _links: {} });
  http.expectOne('/api/notification-overview').flush({ items: [], _links: {} });
  http.expectOne('/api/notification-channels').flush({
    web_push: { available: false, public_key: null },
    email_fallback_configured: false,
    sink_enabled: false,
  });
  http.expectOne('/api/calendar').flush({
    active: false,
    activated_at: null,
    revoked_at: null,
    time_zone: 'Europe/Berlin',
    _links: {},
  });
  http.expectOne('/api/calendar/events').flush({ items: events, _links: {} });
}
