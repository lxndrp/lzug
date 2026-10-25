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

/** Reads and commands consumed by the notifications view. */
export interface PersonalNotificationsPort {
  listNotifications(): Observable<PersonalNotification[]>;
  listNotificationProblems(): Observable<PersonalNotificationProblem[]>;
  listNotificationOverview(): Observable<PersonalNotificationProblem[]>;
  getNotificationChannels(): Observable<PersonalNotificationChannels>;
  registerPushSubscription(endpoint: string): Observable<void>;
}

/** Calendar reads and lifecycle commands owned by the personal calendar view. */
export interface PersonalCalendarPort {
  getCalendarStatus(): Observable<PersonalCalendarStatus>;
  listCalendarEvents(): Observable<PersonalCalendarEvent[]>;
  downloadCalendarEvent(eventId: number): Observable<PersonalCalendarEventDownload>;
  activateCalendarFeed(rotate: boolean): Observable<PersonalCalendarFeedActivation>;
  revokeCalendarFeed(): Observable<PersonalCalendarStatus & { notice: string }>;
}

/** Absence report operations shared by the absence view and exam-day workflow. */
export interface PersonalAbsencePort {
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
}

export const PERSONAL_NOTIFICATIONS_PORT = new InjectionToken<PersonalNotificationsPort>(
  'PERSONAL_NOTIFICATIONS_PORT',
);
export const PERSONAL_CALENDAR_PORT = new InjectionToken<PersonalCalendarPort>(
  'PERSONAL_CALENDAR_PORT',
);
export const PERSONAL_ABSENCE_PORT = new InjectionToken<PersonalAbsencePort>('PERSONAL_ABSENCE_PORT');
