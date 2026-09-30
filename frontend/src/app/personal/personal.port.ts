import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import type {
  CreatePersonalAbsenceReport,
  PersonalAbsenceReport,
  PersonalCalendarEvent,
  PersonalCalendarEventDownload,
  PersonalCalendarFeedActivation,
  PersonalCalendarStatus,
  PersonalNotification,
  PersonalNotificationChannels,
  PersonalNotificationProblem,
} from './personal.models';

/** Personal operations required by notifications, absences, and exam-day features. */
export interface PersonalPort {
  listNotifications(): Observable<PersonalNotification[]>;
  listNotificationProblems(): Observable<PersonalNotificationProblem[]>;
  listNotificationOverview(): Observable<PersonalNotificationProblem[]>;
  getNotificationChannels(): Observable<PersonalNotificationChannels>;
  getCalendarStatus(): Observable<PersonalCalendarStatus>;
  listCalendarEvents(): Observable<PersonalCalendarEvent[]>;
  downloadCalendarEvent(eventId: number): Observable<PersonalCalendarEventDownload>;
  activateCalendarFeed(rotate: boolean): Observable<PersonalCalendarFeedActivation>;
  revokeCalendarFeed(): Observable<PersonalCalendarStatus & { notice: string }>;
  listAbsenceReports(): Observable<PersonalAbsenceReport[]>;
  createAbsenceReport(payload: CreatePersonalAbsenceReport): Observable<PersonalAbsenceReport>;
  answerReplacement(
    responseId: number,
    response: 'available' | 'unavailable',
  ): Observable<PersonalAbsenceReport>;
  selectReplacement(
    reportId: number,
    memberId: number,
    version: number,
  ): Observable<PersonalAbsenceReport>;
  registerPushSubscription(endpoint: string): Observable<void>;
}

export const PERSONAL_PORT = new InjectionToken<PersonalPort>('PERSONAL_PORT');
