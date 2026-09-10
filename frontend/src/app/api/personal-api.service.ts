import type {
  AbsenceReport,
  CalendarEvent,
  CalendarFeedActivation,
  CalendarStatus,
  NotificationChannels,
  NotificationItem,
  NotificationProblem,
} from './personal.models';
import type {
  CalendarFeedActivationRequest,
  PushSubscriptionRequest,
  PushSubscriptionResponse,
} from './generated/types.gen';
import { Injectable, inject } from '@angular/core';

import { ApiClient } from './api-client.service';

/** Own-data notifications, calendars, absences, and replacement responses. */

@Injectable({ providedIn: 'root' })
export class PersonalApiService {
  private readonly client = inject(ApiClient);
  getNotifications() {
    return this.client.list<NotificationItem>('/api/notifications');
  }

  getNotificationProblems() {
    return this.client.list<NotificationProblem>('/api/notification-problems');
  }

  getNotificationOverview() {
    return this.client.list<NotificationProblem>('/api/notification-overview');
  }

  getNotificationChannels() {
    return this.client.get<NotificationChannels>('/api/notification-channels');
  }

  getCalendarStatus() {
    return this.client.get<CalendarStatus>('/api/calendar');
  }

  getCalendarEvents() {
    return this.client.list<CalendarEvent>('/api/calendar/events');
  }

  activateCalendarFeed(rotate = false) {
    return this.client.post<CalendarFeedActivation>('/api/calendar/feed', {
      rotate,
    } satisfies CalendarFeedActivationRequest);
  }

  revokeCalendarFeed() {
    return this.client.delete<CalendarStatus & { notice: string }>('/api/calendar/feed');
  }

  getAbsenceReports() {
    return this.client.list<AbsenceReport>('/api/absence-reports');
  }

  createAbsenceReport(
    examDayId: number,
    assignmentId: number,
    reason?: string,
    dayRevision?: number,
  ) {
    return this.client.post<AbsenceReport>('/api/absence-reports', {
      exam_day_id: examDayId,
      exam_day_assignment_id: assignmentId,
      ...(reason?.trim() ? { reason: reason.trim() } : {}),
      ...(dayRevision ? { day_revision: dayRevision } : {}),
    });
  }

  answerReplacement(responseId: number, response: 'available' | 'unavailable') {
    return this.client.patch<AbsenceReport>(`/api/replacement-responses/${responseId}`, {
      response,
    });
  }

  selectReplacement(reportId: number, memberId: number, version: number) {
    return this.client.post<AbsenceReport>(`/api/absence-reports/${reportId}/select-replacement`, {
      committee_member_id: memberId,
      version,
    });
  }

  registerPushSubscription(endpoint: string) {
    return this.client.post<PushSubscriptionResponse>('/api/push-subscriptions', {
      endpoint,
    } satisfies PushSubscriptionRequest);
  }
}
