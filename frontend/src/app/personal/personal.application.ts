import { Injectable, inject } from '@angular/core';

import { PERSONAL_PORT } from './personal.port';

/** Application operations for notifications, calendars, and absence reports. */
@Injectable({ providedIn: 'root' })
export class PersonalApplication {
  private readonly port = inject(PERSONAL_PORT);

  listNotifications() {
    return this.port.listNotifications();
  }

  listNotificationProblems() {
    return this.port.listNotificationProblems();
  }

  listNotificationOverview() {
    return this.port.listNotificationOverview();
  }

  getNotificationChannels() {
    return this.port.getNotificationChannels();
  }

  getCalendarStatus() {
    return this.port.getCalendarStatus();
  }

  listCalendarEvents() {
    return this.port.listCalendarEvents();
  }

  downloadCalendarEvent(eventId: number) {
    return this.port.downloadCalendarEvent(eventId);
  }

  activateCalendarFeed(rotate: boolean) {
    return this.port.activateCalendarFeed(rotate);
  }

  revokeCalendarFeed() {
    return this.port.revokeCalendarFeed();
  }

  listAbsenceReports() {
    return this.port.listAbsenceReports();
  }

  createAbsenceReport(...args: Parameters<typeof this.port.createAbsenceReport>) {
    return this.port.createAbsenceReport(...args);
  }

  answerReplacement(...args: Parameters<typeof this.port.answerReplacement>) {
    return this.port.answerReplacement(...args);
  }

  selectReplacement(...args: Parameters<typeof this.port.selectReplacement>) {
    return this.port.selectReplacement(...args);
  }

  registerPushSubscription(endpoint: string) {
    return this.port.registerPushSubscription(endpoint);
  }
}
