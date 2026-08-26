import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { forkJoin } from 'rxjs';
import { TuiButton } from '@taiga-ui/core';

import { NotificationChannels, NotificationItem, NotificationProblem } from '../api/api.models';
import { PlanningApiService } from '../api/planning-api.service';

@Component({
  selector: 'app-notifications',
  imports: [DatePipe, TuiButton],
  templateUrl: './notifications.component.html',
  styleUrl: './notifications.component.css',
})
export class NotificationsComponent implements OnInit {
  private readonly api = inject(PlanningApiService);

  protected readonly notifications = signal<NotificationItem[]>([]);
  protected readonly problems = signal<NotificationProblem[]>([]);
  protected readonly channels = signal<NotificationChannels | null>(null);
  protected readonly loading = signal(true);
  protected readonly pushBusy = signal(false);
  protected readonly pushMessage = signal<string | null>(null);

  ngOnInit(): void {
    forkJoin({
      notifications: this.api.getNotifications(),
      problems: this.api.getNotificationOverview(),
      channels: this.api.getNotificationChannels(),
    }).subscribe({
      next: ({ notifications, problems, channels }) => {
        this.notifications.set(notifications);
        this.problems.set(problems);
        this.channels.set(channels);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.pushMessage.set('Benachrichtigungen konnten nicht geladen werden.');
      },
    });
  }

  protected canEnablePush(): boolean {
    return (
      this.channels()?.web_push.available === true &&
      typeof navigator !== 'undefined' &&
      'serviceWorker' in navigator &&
      'PushManager' in window
    );
  }

  protected async enablePush(): Promise<void> {
    const publicKey = this.channels()?.web_push.public_key;
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
        this.api.registerPushSubscription(subscription.endpoint).subscribe({
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

  protected statusLabel(status: NotificationProblem['status']): string {
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
