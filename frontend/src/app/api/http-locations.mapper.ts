import type { MasterData } from './api.models';
import type {
  ExamRoomResponse as ApiRoom,
  ExamVenueContactResponse as ApiContact,
  ExamVenueResponse as ApiVenue,
} from './generated/types.gen';
import type {
  ExamRoom as ProjectionRoom,
  ExamVenue as ProjectionVenue,
  ExamVenueContact as ProjectionContact,
} from './master-data.models';
import type {
  LocationSnapshot,
  Venue,
  VenueContact,
  VenueRoom,
} from '../locations/locations.models';

export function toVenue(value: ApiVenue | ProjectionVenue): Venue {
  const mapProvider = record(value.map_provider ?? { mode: 'off' }, 'map_provider');
  const capabilities = record(value['capabilities'], 'capabilities');
  return {
    id: value.id,
    scope: oneOf(value.scope, ['global', 'committee'], 'scope'),
    committeeId: value.committee_id,
    committeeName: value.committee_name ?? null,
    name: value.name,
    street: value.street,
    postalCode: value.postal_code,
    city: value.city,
    country: value.country,
    siteName: value.site_name,
    entrance: value.entrance,
    travelDirections: value.travel_directions,
    isAccessible: value.is_accessible === null ? null : value.is_accessible === 1,
    accessibilityStatus: oneOf(
      value.accessibility_status,
      ['confirmed', 'needs_clarification'],
      'accessibility_status',
    ),
    accessibilityNotes: value.accessibility_notes,
    latitude: value.latitude ?? null,
    longitude: value.longitude ?? null,
    coordinateStatus: oneOf(
      value.coordinate_status,
      ['missing', 'needs_review', 'confirmed'],
      'coordinate_status',
    ),
    coordinateSource: value.coordinate_source ?? null,
    isActive: value.is_active === 1,
    revision: value.revision,
    ...(typeof value['consequence_warning'] === 'string'
      ? { consequenceWarning: value['consequence_warning'] }
      : {}),
    rooms: value.rooms.map(toRoom),
    contacts: value.contacts.map(toContact),
    consequenceProblems: optionalRecordArray(value['consequence_problems']).map((problem) => ({
      auditId: requiredNumber(problem, 'audit_id'),
      venueId: requiredNumber(problem, 'venue_id'),
      entityType: oneOf(requiredString(problem, 'entity_type'), ['venue', 'room'], 'entity_type'),
      entityId: requiredNumber(problem, 'entity_id'),
      consequenceType: oneOf(
        requiredString(problem, 'consequence_type'),
        ['calendar', 'notification', 'derivation'],
        'consequence_type',
      ),
      status: oneOf(
        requiredString(problem, 'status'),
        ['temporarily_failed', 'permanently_failed'],
        'status',
      ),
      attemptCount: requiredNumber(problem, 'attempt_count'),
      errorCode: nullableString(problem, 'error_code'),
      updatedAt: requiredString(problem, 'updated_at'),
      retryable: requiredBoolean(problem, 'retryable'),
    })),
    mapProvider: {
      mode: oneOf(mapProvider['mode'], ['off', 'osm', 'google'], 'map_provider.mode'),
      ...(typeof mapProvider['attribution'] === 'string'
        ? { attribution: mapProvider['attribution'] }
        : {}),
      ...(typeof mapProvider['attribution_url'] === 'string'
        ? { attributionUrl: mapProvider['attribution_url'] }
        : {}),
    },
    capabilities: {
      manage: requiredBoolean(capabilities, 'manage'),
      retryConsequences: optionalBoolean(capabilities, 'retry_consequences') ?? false,
      geocode: optionalBoolean(capabilities, 'geocode') ?? false,
      requestPromotion: requiredBoolean(capabilities, 'request_promotion'),
      decidePromotion: requiredBoolean(capabilities, 'decide_promotion'),
    },
  };
}

export function toLocationSnapshot(
  value: Pick<MasterData, 'committees' | 'examVenues' | 'examVenuesCanCreate'>,
): LocationSnapshot {
  return {
    committees: value.committees.map(({ id, name }) => ({ id, name })),
    committeeLoadPending: false,
    committeeLoadError: false,
    venues: value.examVenues.map(toVenue),
    canCreateVenue: Boolean(value.examVenuesCanCreate),
  };
}

export function toRoom(value: ApiRoom | ProjectionRoom): VenueRoom {
  return {
    id: value.id,
    venueId: value.venue_id,
    name: value.name,
    building: value.building,
    wing: value.wing,
    floor: value.floor,
    roomNumber: value.room_number,
    accessNotes: value.access_notes,
    capacity: value.capacity,
    isActive: value.is_active === 1,
    revision: value.revision,
    ...(typeof value['consequence_warning'] === 'string'
      ? { consequenceWarning: value['consequence_warning'] }
      : {}),
  };
}

function oneOf<const T extends readonly string[]>(
  value: unknown,
  options: T,
  field: string,
): T[number] {
  const match = options.find((option) => option === value);
  if (match !== undefined) return match;
  throw new Error(`Unsupported ${field}: ${String(value)}`);
}

function record(value: unknown, field: string): Record<string, unknown> {
  if (isRecord(value)) return value;
  throw new Error(`Expected ${field} to be an object`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function optionalRecordArray(value: unknown): Record<string, unknown>[] {
  if (value === undefined) return [];
  if (Array.isArray(value)) return value.map((item) => record(item, 'consequence problem'));
  throw new Error('Expected consequence_problems to be an array');
}

function requiredString(source: Record<string, unknown>, key: string): string {
  const value = source[key];
  if (typeof value === 'string') return value;
  throw new Error(`Expected ${key} to be a string`);
}

function nullableString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key];
  if (value === null || typeof value === 'string') return value;
  throw new Error(`Expected ${key} to be a string or null`);
}

function requiredNumber(source: Record<string, unknown>, key: string): number {
  const value = source[key];
  if (typeof value === 'number') return value;
  throw new Error(`Expected ${key} to be a number`);
}

function requiredBoolean(source: Record<string, unknown>, key: string): boolean {
  const value = source[key];
  if (typeof value === 'boolean') return value;
  throw new Error(`Expected ${key} to be a boolean`);
}

function optionalBoolean(source: Record<string, unknown>, key: string): boolean | undefined {
  const value = source[key];
  if (value === undefined || typeof value === 'boolean') return value;
  throw new Error(`Expected ${key} to be a boolean`);
}

export function toContact(value: ApiContact | ProjectionContact): VenueContact {
  return {
    id: value.id,
    venueId: value.venue_id,
    label: value.label,
    role: value.role,
    phone: value.phone,
    email: value.email,
    availabilityNotes: value.availability_notes,
    isActive: value.is_active === 1,
    revision: value.revision,
    roomIds: value.room_ids,
  };
}
