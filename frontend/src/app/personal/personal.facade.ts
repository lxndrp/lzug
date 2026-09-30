import { Injectable, inject } from '@angular/core';

import { PersonalApplication } from './personal.application';

/** UI-facing personal operations shared by notifications, absences, and exam day. */
@Injectable({ providedIn: 'root' })
export class PersonalFacade {
  private readonly application = inject(PersonalApplication);

  listNotifications() {
    return this.application.listNotifications();
  }

  listNotificationProblems() {
    return this.application.listNotificationProblems();
  }

  listNotificationOverview() {
    return this.application.listNotificationOverview();
  }

  getNotificationChannels() {
    return this.application.getNotificationChannels();
  }

  getCalendarStatus() {
    return this.application.getCalendarStatus();
  }

  listCalendarEvents() {
    return this.application.listCalendarEvents();
  }

  downloadCalendarEvent(eventId: number) {
    return this.application.downloadCalendarEvent(eventId);
  }

  activateCalendarFeed(rotate = false) {
    return this.application.activateCalendarFeed(rotate);
  }

  revokeCalendarFeed() {
    return this.application.revokeCalendarFeed();
  }

  listAbsenceReports() {
    return this.application.listAbsenceReports();
  }

  createAbsenceReport(...args: Parameters<PersonalApplication['createAbsenceReport']>) {
    return this.application.createAbsenceReport(...args);
  }

  answerReplacement(...args: Parameters<PersonalApplication['answerReplacement']>) {
    return this.application.answerReplacement(...args);
  }

  selectReplacement(...args: Parameters<PersonalApplication['selectReplacement']>) {
    return this.application.selectReplacement(...args);
  }

  registerPushSubscription(endpoint: string) {
    return this.application.registerPushSubscription(endpoint);
  }
}
