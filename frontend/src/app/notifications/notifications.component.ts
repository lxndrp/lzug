import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { forkJoin } from 'rxjs';
import { TuiButton } from '@taiga-ui/core';

import type {
  PersonalCalendarEvent,
  PersonalCalendarFeedActivation,
  PersonalCalendarStatus,
  PersonalNotification,
  PersonalNotificationChannels,
  PersonalNotificationProblem,
} from '../personal/personal.models';
import { PersonalFacade } from '../personal/personal.facade';
import { AuthService } from '../auth/auth.service';

@Component({
  selector: 'app-notifications',
  imports: [DatePipe, TuiButton],
  templateUrl: './notifications.component.html',
  styleUrl: './notifications.component.css',
})
export class NotificationsComponent implements OnInit {
  private readonly personal = inject(PersonalFacade);
  private readonly auth = inject(AuthService);

  protected readonly notifications = signal<PersonalNotification[]>([]);
  protected readonly problems = signal<PersonalNotificationProblem[]>([]);
  protected readonly channels = signal<PersonalNotificationChannels | null>(null);
  protected readonly loading = signal(true);
  protected readonly pushBusy = signal(false);
  protected readonly pushMessage = signal<string | null>(null);
  protected readonly calendar = signal<PersonalCalendarStatus | null>(null);
  protected readonly calendarEvents = signal<PersonalCalendarEvent[]>([]);
  protected readonly calendarBusy = signal(false);
  protected readonly calendarEventBusy = signal<number | null>(null);
  protected readonly calendarMessage = signal<string | null>(null);
  protected readonly feedUrl = signal<string | null>(null);

  ngOnInit(): void {
    forkJoin({
      notifications: this.personal.listNotifications(),
      problems: this.personal.listNotificationOverview(),
      channels: this.personal.getNotificationChannels(),
      calendar: this.personal.getCalendarStatus(),
      calendarEvents: this.personal.listCalendarEvents(),
    }).subscribe({
      next: ({ notifications, problems, channels, calendar, calendarEvents }) => {
        this.notifications.set(notifications);
        this.problems.set(problems);
        this.channels.set(channels);
        this.calendar.set(calendar);
        this.calendarEvents.set(calendarEvents);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.pushMessage.set('Benachrichtigungen konnten nicht geladen werden.');
      },
    });
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
    this.personal.activateCalendarFeed(rotate).subscribe({
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
    this.personal.revokeCalendarFeed().subscribe({
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
    this.personal.downloadCalendarEvent(eventId).subscribe({
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
        this.pushMessage.set('Der Kalendereintrag konnte nicht heruntergeladen werden.');
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
    this.pushBusy.set(true);
    this.pushMessage.set(null);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        this.pushMessage.set('Browser-Benachrichtigungen wurden nicht erlaubt.');
        return;
      }
      const registration = await navigator.serviceWorker.register('/notification-sw.js');
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: this.decodeKey(publicKey),
      });
      await new Promise<void>((resolve, reject) => {
        this.personal.registerPushSubscription(subscription.endpoint).subscribe({
          next: () => resolve(),
          error: reject,
        });
      });
      this.pushMessage.set('Browser-Benachrichtigungen sind aktiviert.');
    } catch {
      this.pushMessage.set('Browser-Benachrichtigungen konnten nicht aktiviert werden.');
    } finally {
      this.pushBusy.set(false);
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
