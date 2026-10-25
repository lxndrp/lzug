import { DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TuiButton } from '@taiga-ui/core';

import { AuthService } from '../auth/auth.service';
import { SessionScopeService } from '../auth/session-scope.service';
import type {
  PersonalCalendarEvent,
  PersonalCalendarFeedActivation,
  PersonalCalendarStatus,
  PersonalNotification,
  PersonalNotificationChannels,
  PersonalNotificationProblem,
} from '../personal/personal.models';
import { PERSONAL_CALENDAR_PORT, PERSONAL_NOTIFICATIONS_PORT } from '../personal/personal.port';

@Component({
  selector: 'app-notifications',
  imports: [DatePipe, TuiButton],
  templateUrl: './notifications.component.html',
  styleUrl: './notifications.component.css',
})
export class NotificationsComponent implements OnInit {
  private readonly notificationsPort = inject(PERSONAL_NOTIFICATIONS_PORT);
  private readonly calendarPort = inject(PERSONAL_CALENDAR_PORT);
  private readonly auth = inject(AuthService);
  private readonly sessionScope = inject(SessionScopeService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly notifications = signal<PersonalNotification[]>([]);
  protected readonly problems = signal<PersonalNotificationProblem[]>([]);
  protected readonly channels = signal<PersonalNotificationChannels | null>(null);
  protected readonly notificationsLoading = signal(true);
  protected readonly problemsLoading = signal(true);
  protected readonly channelsLoading = signal(true);
  protected readonly calendarLoading = signal(true);
  protected readonly calendarEventsLoading = signal(true);
  protected readonly pushBusy = signal(false);
  protected readonly pushMessage = signal<string | null>(null);
  protected readonly calendar = signal<PersonalCalendarStatus | null>(null);
  protected readonly calendarEvents = signal<PersonalCalendarEvent[]>([]);
  protected readonly calendarBusy = signal(false);
  protected readonly calendarEventBusy = signal<number | null>(null);
  protected readonly calendarMessage = signal<string | null>(null);
  protected readonly feedUrl = signal<string | null>(null);
  protected readonly notificationError = signal<string | null>(null);
  protected readonly problemError = signal<string | null>(null);
  protected readonly channelError = signal<string | null>(null);
  protected readonly calendarError = signal<string | null>(null);
  protected readonly calendarEventsError = signal<string | null>(null);

  ngOnInit(): void {
    this.sessionScope.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((change) => {
      this.clearPersonalData();
      queueMicrotask(() => {
        if (change.generation !== this.sessionScope.generation()) return;
        if (this.auth.session()?.authenticated) this.load();
        else {
          this.notificationsLoading.set(false);
          this.problemsLoading.set(false);
          this.channelsLoading.set(false);
          this.calendarLoading.set(false);
          this.calendarEventsLoading.set(false);
        }
      });
    });
    this.load();
  }

  private load(): void {
    const generation = this.sessionScope.generation();
    this.notificationsLoading.set(true);
    this.problemsLoading.set(true);
    this.channelsLoading.set(true);
    this.calendarLoading.set(true);
    this.calendarEventsLoading.set(true);
    const settle = (loading: typeof this.notificationsLoading) => {
      if (this.sessionScope.generation() === generation) loading.set(false);
    };
    this.sessionScope.forCurrentSession(this.notificationsPort.listNotifications()).subscribe({
      next: (value) => {
        if (generation === this.sessionScope.generation()) this.notifications.set(value);
        settle(this.notificationsLoading);
      },
      error: () => {
        if (generation === this.sessionScope.generation())
          this.notificationError.set('Benachrichtigungen konnten nicht geladen werden.');
        settle(this.notificationsLoading);
      },
    });
    this.sessionScope
      .forCurrentSession(this.notificationsPort.listNotificationOverview())
      .subscribe({
        next: (value) => {
          if (generation === this.sessionScope.generation()) this.problems.set(value);
          settle(this.problemsLoading);
        },
        error: () => {
          if (generation === this.sessionScope.generation())
            this.problemError.set('Zustellstatus konnte nicht geladen werden.');
          settle(this.problemsLoading);
        },
      });
    this.sessionScope
      .forCurrentSession(this.notificationsPort.getNotificationChannels())
      .subscribe({
        next: (value) => {
          if (generation === this.sessionScope.generation()) this.channels.set(value);
          settle(this.channelsLoading);
        },
        error: () => {
          if (generation === this.sessionScope.generation())
            this.channelError.set('Benachrichtigungseinstellungen konnten nicht geladen werden.');
          settle(this.channelsLoading);
        },
      });
    this.sessionScope.forCurrentSession(this.calendarPort.getCalendarStatus()).subscribe({
      next: (value) => {
        if (generation === this.sessionScope.generation()) this.calendar.set(value);
        settle(this.calendarLoading);
      },
      error: () => {
        if (generation === this.sessionScope.generation())
          this.calendarError.set('Kalenderzugang konnte nicht geladen werden.');
        settle(this.calendarLoading);
      },
    });
    this.sessionScope.forCurrentSession(this.calendarPort.listCalendarEvents()).subscribe({
      next: (value) => {
        if (generation === this.sessionScope.generation()) this.calendarEvents.set(value);
        settle(this.calendarEventsLoading);
      },
      error: () => {
        if (generation === this.sessionScope.generation())
          this.calendarEventsError.set('Kalendereinträge konnten nicht geladen werden.');
        settle(this.calendarEventsLoading);
      },
    });
  }

  private clearPersonalData(): void {
    this.notifications.set([]);
    this.problems.set([]);
    this.channels.set(null);
    this.calendar.set(null);
    this.calendarEvents.set([]);
    this.feedUrl.set(null);
    this.notificationsLoading.set(true);
    this.problemsLoading.set(true);
    this.channelsLoading.set(true);
    this.calendarLoading.set(true);
    this.calendarEventsLoading.set(true);
    this.pushBusy.set(false);
    this.pushMessage.set(null);
    this.calendarBusy.set(false);
    this.calendarEventBusy.set(null);
    this.calendarMessage.set(null);
    this.notificationError.set(null);
    this.problemError.set(null);
    this.channelError.set(null);
    this.calendarError.set(null);
    this.calendarEventsError.set(null);
  }

  protected activateCalendar(rotate = false): void {
    if (!this.canManageCalendarFeed() || this.calendarBusy()) return;
    if (
      rotate &&
      !window.confirm('Der bisherige Kalenderzugang wird sofort ungültig. Fortfahren?')
    ) {
      return;
    }
    this.calendarBusy.set(true);
    this.calendarMessage.set(null);
    this.sessionScope.forCurrentSession(this.calendarPort.activateCalendarFeed(rotate)).subscribe({
      next: (result: PersonalCalendarFeedActivation) => {
        this.calendar.set(result);
        this.feedUrl.set(result.feedUrl);
        this.calendarMessage.set(result.notice);
        this.calendarBusy.set(false);
      },
      error: () => {
        this.calendarMessage.set('Der persönliche Kalenderzugang konnte nicht aktiviert werden.');
        this.calendarBusy.set(false);
      },
    });
  }

  protected revokeCalendar(): void {
    if (!this.canManageCalendarFeed() || this.calendarBusy()) return;
    if (!window.confirm('Der Kalenderzugang wird sofort ungültig. Fortfahren?')) return;
    this.calendarBusy.set(true);
    this.calendarMessage.set(null);
    this.sessionScope.forCurrentSession(this.calendarPort.revokeCalendarFeed()).subscribe({
      next: (result) => {
        this.calendar.set(result);
        this.feedUrl.set(null);
        this.calendarMessage.set(result.notice);
        this.calendarBusy.set(false);
      },
      error: () => {
        this.calendarMessage.set('Der persönliche Kalenderzugang konnte nicht widerrufen werden.');
        this.calendarBusy.set(false);
      },
    });
  }

  protected calendarStatusLabel(event: PersonalCalendarEvent): string {
    return event.status === 'cancelled'
      ? 'Storniert'
      : event.status === 'updated'
        ? 'Geändert'
        : 'Bestätigt';
  }

  protected downloadCalendarEvent(eventId: number): void {
    if (this.calendarEventBusy() !== null) return;
    this.calendarEventBusy.set(eventId);
    this.sessionScope
      .forCurrentSession(this.calendarPort.downloadCalendarEvent(eventId))
      .subscribe({
        next: ({ content, mediaType, fileName }) => {
          const url = URL.createObjectURL(new Blob([content], { type: mediaType }));
          const link = document.createElement('a');
          link.href = url;
          link.download = fileName;
          link.click();
          window.setTimeout(() => URL.revokeObjectURL(url), 0);
          this.calendarEventBusy.set(null);
        },
        error: () => {
          this.calendarMessage.set('Der Kalendereintrag konnte nicht heruntergeladen werden.');
          this.calendarEventBusy.set(null);
        },
      });
  }

  protected canEnablePush(): boolean {
    return (
      this.canManagePush() &&
      this.channels()?.webPush.available === true &&
      typeof navigator !== 'undefined' &&
      'serviceWorker' in navigator &&
      'PushManager' in window
    );
  }

  protected async enablePush(): Promise<void> {
    const publicKey = this.channels()?.webPush.publicKey;
    if (!publicKey || !this.canEnablePush()) return;
    const generation = this.sessionScope.generation();
    this.pushBusy.set(true);
    this.pushMessage.set(null);
    try {
      const permission = await Notification.requestPermission();
      if (generation !== this.sessionScope.generation()) return;
      if (permission !== 'granted') {
        this.pushMessage.set('Browser-Benachrichtigungen wurden nicht erlaubt.');
        return;
      }
      const registration = await navigator.serviceWorker.register('/notification-sw.js');
      if (generation !== this.sessionScope.generation()) return;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: this.decodeKey(publicKey),
      });
      if (generation !== this.sessionScope.generation()) return;
      await new Promise<void>((resolve, reject) => {
        this.sessionScope
          .forCurrentSession(this.notificationsPort.registerPushSubscription(subscription.endpoint))
          .subscribe({
            next: () => resolve(),
            error: reject,
            complete: resolve,
          });
      });
      if (generation === this.sessionScope.generation()) {
        this.pushMessage.set('Browser-Benachrichtigungen sind aktiviert.');
      }
    } catch {
      if (generation === this.sessionScope.generation()) {
        this.pushMessage.set('Browser-Benachrichtigungen konnten nicht aktiviert werden.');
      }
    } finally {
      if (generation === this.sessionScope.generation()) this.pushBusy.set(false);
    }
  }

  protected canManagePush(): boolean {
    return this.auth.hasCapability('push:manage-own');
  }

  protected canManageCalendarFeed(): boolean {
    return this.auth.hasCapability('calendar:feed-manage-own');
  }

  protected statusLabel(status: PersonalNotificationProblem['status']): string {
    return {
      pending: 'Ausstehend',
      technically_confirmed: 'Technisch bestätigt',
      temporarily_failed: 'Vorübergehend fehlgeschlagen',
      permanently_failed: 'Endgültig fehlgeschlagen',
      unavailable: 'Nicht verfügbar',
    }[status];
  }

  private decodeKey(value: string): Uint8Array<ArrayBuffer> {
    const padded = value
      .replace(/-/g, '+')
      .replace(/_/g, '/')
      .padEnd(value.length + ((4 - (value.length % 4)) % 4), '=');
    const decoded = atob(padded);
    return Uint8Array.from(decoded, (character) => character.charCodeAt(0));
  }
}
