/** Personal notification, calendar, and absence data used by the application. */
export type PersonalNotification = {
  id: number;
  eventType: string;
  title: string;
  message: string;
  actionPath: string;
  createdAt: string;
};

export type PersonalNotificationProblem = {
  notificationId: number;
  eventType: string;
  recipientMemberId: number;
  channel: 'web_push' | 'email' | 'sink';
  status:
    | 'pending'
    | 'technically_confirmed'
    | 'temporarily_failed'
    | 'permanently_failed'
    | 'unavailable';
  attemptCount: number;
  errorCode: string | null;
  updatedAt: string;
};

export type PersonalNotificationChannels = {
  emailFallbackConfigured: boolean;
  sinkEnabled: boolean;
  webPush: { available: boolean; publicKey: string | null };
};

export type PersonalCalendarStatus = {
  activatedAt: string | null;
  active: boolean;
  revokedAt: string | null;
  timeZone: string;
};

export type PersonalCalendarEvent = {
  id: number;
  externalEventId: string;
  date: string;
  startsAt: string;
  endsAt: string;
  timeZone: string;
  location: string;
  role: string;
  roundName: string;
  status: 'sent' | 'updated' | 'cancelled' | string;
  version: number;
};

export type PersonalCalendarEventDownload = {
  content: string;
  mediaType: string;
  fileName: string;
};

export type PersonalCalendarFeedActivation = PersonalCalendarStatus & {
  feedUrl: string;
  notice: string;
};

export type PersonalAbsenceResponse = {
  id: number;
  committeeMemberId: number;
  response: 'pending' | 'available' | 'unavailable' | string;
  requestedAt: string;
  expiresAt: string | null;
  urgent: boolean;
  respondedAt: string | null;
};

export type PersonalAbsenceReport = {
  id: number;
  examDayId: number;
  examDayAssignmentId: number;
  committeeMemberId: number;
  reportedByMemberId: number;
  reportedAt: string;
  reason: string | null;
  status: string;
  selectedReplacementMemberId: number | null;
  version: number;
  createdAt: string;
  updatedAt: string;
  responses: PersonalAbsenceResponse[];
  audit: Array<{
    id: number;
    actorMemberId: number;
    eventType: string;
    fromStatus: string | null;
    toStatus: string | null;
    details: string | null;
    createdAt: string;
  }>;
};

export type CreatePersonalAbsenceReport = {
  examDayId: number;
  assignmentId: number;
  reason?: string;
  dayRevision?: number;
};
