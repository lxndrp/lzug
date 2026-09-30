import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { catchError, map, throwError } from 'rxjs';

import type {
  AbsenceReport as ApiAbsenceReport,
  CalendarEvent as ApiCalendarEvent,
  CalendarFeedActivation as ApiCalendarFeedActivation,
  CalendarStatus as ApiCalendarStatus,
  NotificationChannels as ApiNotificationChannels,
  NotificationItem as ApiNotification,
  NotificationProblem as ApiNotificationProblem,
} from './personal.models';
import type { CalendarFeedActivationRequest, PushSubscriptionRequest } from './generated/types.gen';
import { ApiClient } from './api-client.service';
import { toApplicationError } from './application-error';
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
} from '../personal/personal.models';
import type { PersonalPort } from '../personal/personal.port';

/** HTTP/OpenAPI adapter for the transport-neutral personal feature port. */
@Injectable({ providedIn: 'root' })
export class HttpPersonalAdapter implements PersonalPort {
  private readonly client = inject(ApiClient);
  private readonly http = inject(HttpClient);

  listNotifications() {
    return this.client
      .list<ApiNotification>('/api/notifications')
      .pipe(map((items) => items.map(toNotification)));
  }

  listNotificationProblems() {
    return this.client
      .list<ApiNotificationProblem>('/api/notification-problems')
      .pipe(map((items) => items.map(toNotificationProblem)));
  }

  listNotificationOverview() {
    return this.client
      .list<ApiNotificationProblem>('/api/notification-overview')
      .pipe(map((items) => items.map(toNotificationProblem)));
  }

  getNotificationChannels() {
    return this.client
      .get<ApiNotificationChannels>('/api/notification-channels')
      .pipe(map(toNotificationChannels));
  }

  getCalendarStatus() {
    return this.client.get<ApiCalendarStatus>('/api/calendar').pipe(map(toCalendarStatus));
  }

  listCalendarEvents() {
    return this.client
      .list<ApiCalendarEvent>('/api/calendar/events')
      .pipe(map((items) => items.map(toCalendarEvent)));
  }

  downloadCalendarEvent(eventId: number) {
    return this.http
      .get(`/api/calendar/events/${eventId}.ics`, { observe: 'response', responseType: 'text' })
      .pipe(
        map((response): PersonalCalendarEventDownload => ({
          content: response.body ?? '',
          mediaType: response.headers.get('content-type') ?? 'text/calendar; charset=utf-8',
          fileName:
            response.headers.get('content-disposition')?.match(/filename="?([^";]+)"?/i)?.[1] ??
            `calendar-event-${eventId}.ics`,
        })),
        catchError((error: unknown) => throwError(() => toApplicationError(error))),
      );
  }

  activateCalendarFeed(rotate: boolean) {
    return this.client
      .post<ApiCalendarFeedActivation>('/api/calendar/feed', {
        rotate,
      } satisfies CalendarFeedActivationRequest)
      .pipe(map(toCalendarActivation));
  }

  revokeCalendarFeed() {
    return this.client
      .delete<ApiCalendarStatus & { notice: string }>('/api/calendar/feed')
      .pipe(map((value) => ({ ...toCalendarStatus(value), notice: value.notice })));
  }

  listAbsenceReports() {
    return this.client
      .list<ApiAbsenceReport>('/api/absence-reports')
      .pipe(map((items) => items.map(toAbsenceReport)));
  }

  createAbsenceReport(payload: CreatePersonalAbsenceReport) {
    return this.client
      .post<ApiAbsenceReport>('/api/absence-reports', {
        exam_day_id: payload.examDayId,
        exam_day_assignment_id: payload.assignmentId,
        ...(payload.reason?.trim() ? { reason: payload.reason.trim() } : {}),
        ...(payload.dayRevision ? { day_revision: payload.dayRevision } : {}),
      })
      .pipe(map(toAbsenceReport));
  }

  answerReplacement(responseId: number, response: 'available' | 'unavailable') {
    return this.client
      .patch<ApiAbsenceReport>(`/api/replacement-responses/${responseId}`, { response })
      .pipe(map(toAbsenceReport));
  }

  selectReplacement(reportId: number, memberId: number, version: number) {
    return this.client
      .post<ApiAbsenceReport>(`/api/absence-reports/${reportId}/select-replacement`, {
        committee_member_id: memberId,
        version,
      })
      .pipe(map(toAbsenceReport));
  }

  registerPushSubscription(endpoint: string) {
    return this.client
      .post('/api/push-subscriptions', { endpoint } satisfies PushSubscriptionRequest)
      .pipe(map(() => undefined));
  }
}

function toNotification(value: ApiNotification): PersonalNotification {
  return {
    id: value.id,
    eventType: value.event_type,
    title: value.title,
    message: value.message,
    actionPath: value.action_path,
    createdAt: value.created_at,
  };
}

function toNotificationProblem(value: ApiNotificationProblem): PersonalNotificationProblem {
  return {
    notificationId: value.notification_id,
    eventType: value.event_type,
    recipientMemberId: value.recipient_member_id,
    channel: value.channel,
    status: value.status,
    attemptCount: value.attempt_count,
    errorCode: value.error_code,
    updatedAt: value.updated_at,
  };
}

function toNotificationChannels(value: ApiNotificationChannels): PersonalNotificationChannels {
  return {
    emailFallbackConfigured: value.email_fallback_configured,
    sinkEnabled: value.sink_enabled,
    webPush: { available: value.web_push.available, publicKey: value.web_push.public_key },
  };
}

function toCalendarStatus(value: ApiCalendarStatus): PersonalCalendarStatus {
  return {
    activatedAt: value.activated_at,
    active: value.active,
    revokedAt: value.revoked_at,
    timeZone: value.time_zone,
  };
}

function toCalendarActivation(value: ApiCalendarFeedActivation): PersonalCalendarFeedActivation {
  return { ...toCalendarStatus(value), feedUrl: value.feed_url, notice: value.notice };
}

function toCalendarEvent(value: ApiCalendarEvent): PersonalCalendarEvent {
  return {
    id: value.id,
    externalEventId: value.external_event_id,
    date: value.date,
    startsAt: value.starts_at,
    endsAt: value.ends_at,
    timeZone: value.time_zone,
    location: value.location,
    role: value.role,
    roundName: value.round_name,
    status: value.status,
    version: value.version,
  };
}

function toAbsenceReport(value: ApiAbsenceReport): PersonalAbsenceReport {
  return {
    id: value.id,
    examDayId: value.exam_day_id,
    examDayAssignmentId: value.exam_day_assignment_id,
    committeeMemberId: value.committee_member_id,
    reportedByMemberId: value.reported_by_member_id,
    reportedAt: value.reported_at,
    reason: value.reason,
    status: value.status,
    selectedReplacementMemberId: value.selected_replacement_member_id,
    version: value.version,
    createdAt: value.created_at,
    updatedAt: value.updated_at,
    responses: value.responses.map((response) => ({
      id: response.id,
      committeeMemberId: response.committee_member_id,
      response: response.response,
      requestedAt: response.requested_at,
      expiresAt: response.expires_at,
      urgent: response.urgent,
      respondedAt: response.responded_at,
    })),
    audit: value.audit.map((entry) => ({
      id: entry.id,
      actorMemberId: entry.actor_member_id,
      eventType: entry.event_type,
      fromStatus: entry.from_status,
      toStatus: entry.to_status,
      details: entry.details,
      createdAt: entry.created_at,
    })),
  };
}
