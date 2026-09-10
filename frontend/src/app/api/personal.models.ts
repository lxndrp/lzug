import type { ApiLink } from './common.models';
import type {
  CalendarFeedActivationResponse,
  CalendarStatusResponse,
  NotificationChannelsResponse,
} from './generated/types.gen';

export type NotificationItem = {
  id: number;
  event_type: string;
  title: string;
  message: string;
  action_path: string;
  created_at: string;
};

export type AbsenceResponse = {
  id: number;
  committee_member_id: number;
  response: 'pending' | 'available' | 'unavailable' | string;
  requested_at: string;
  expires_at: string | null;
  urgent: boolean;
  responded_at: string | null;
};

export type AbsenceReport = {
  id: number;
  exam_day_id: number;
  exam_day_assignment_id: number;
  committee_member_id: number;
  reported_by_member_id: number;
  reported_at: string;
  reason: string | null;
  status: string;
  selected_replacement_member_id: number | null;
  version: number;
  created_at: string;
  updated_at: string;
  responses: AbsenceResponse[];
  audit: Array<{
    id: number;
    actor_member_id: number;
    event_type: string;
    from_status: string | null;
    to_status: string | null;
    details: string | null;
    created_at: string;
  }>;
};

export type NotificationProblem = {
  notification_id: number;
  event_type: string;
  recipient_member_id: number;
  channel: 'web_push' | 'email' | 'sink';
  status:
    | 'pending'
    | 'technically_confirmed'
    | 'temporarily_failed'
    | 'permanently_failed'
    | 'unavailable';
  attempt_count: number;
  error_code: string | null;
  updated_at: string;
};

export type NotificationChannels = NotificationChannelsResponse & {
  web_push: { available: boolean; public_key: string | null };
};

export type CalendarStatus = CalendarStatusResponse & {
  _links: Record<string, ApiLink>;
};

export type CalendarEvent = {
  id: number;
  external_event_id: string;
  date: string;
  starts_at: string;
  ends_at: string;
  time_zone: string;
  location: string;
  role: string;
  round_name: string;
  status: 'sent' | 'updated' | 'cancelled' | string;
  version: number;
  download_url: string;
};

export type CalendarFeedActivation = CalendarFeedActivationResponse & {
  _links: Record<string, ApiLink>;
};
