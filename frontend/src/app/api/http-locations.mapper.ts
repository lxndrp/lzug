import type { MasterData } from './api.models';
import type {
  ExamRoom as ApiRoom,
  ExamVenue as ApiVenue,
  ExamVenueContact as ApiContact,
} from './master-data.models';
import type {
  LocationSnapshot,
  Venue,
  VenueContact,
  VenueRoom,
} from '../locations/locations.models';

export function toVenue(value: ApiVenue): Venue {
  return {
    id: value.id,
    scope: value.scope,
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
    accessibilityStatus: value.accessibility_status,
    accessibilityNotes: value.accessibility_notes,
    latitude: value.latitude ?? null,
    longitude: value.longitude ?? null,
    coordinateStatus: value.coordinate_status ?? 'missing',
    coordinateSource: value.coordinate_source ?? null,
    isActive: value.is_active === 1,
    revision: value.revision,
    ...(typeof value.consequence_warning === 'string'
      ? { consequenceWarning: value.consequence_warning }
      : {}),
    rooms: value.rooms.map(toRoom),
    contacts: value.contacts.map(toContact),
    consequenceProblems: (value.consequence_problems ?? []).map((problem) => ({
      auditId: problem.audit_id,
      venueId: problem.venue_id,
      entityType: problem.entity_type,
      entityId: problem.entity_id,
      consequenceType: problem.consequence_type,
      status: problem.status,
      attemptCount: problem.attempt_count,
      errorCode: problem.error_code,
      updatedAt: problem.updated_at,
    })),
    mapProvider: {
      mode: value.map_provider?.mode ?? 'off',
      ...(value.map_provider?.attribution !== undefined
        ? { attribution: value.map_provider.attribution }
        : {}),
      ...(value.map_provider?.attribution_url !== undefined
        ? { attributionUrl: value.map_provider.attribution_url }
        : {}),
    },
    capabilities: {
      manage: value.capabilities.manage,
      retryConsequences: value.capabilities.retry_consequences ?? false,
      geocode: value.capabilities.geocode ?? false,
      requestPromotion: value.capabilities.request_promotion,
      decidePromotion: value.capabilities.decide_promotion,
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

export function toRoom(value: ApiRoom): VenueRoom {
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
    ...(typeof value.consequence_warning === 'string'
      ? { consequenceWarning: value.consequence_warning }
      : {}),
  };
}

export function toContact(value: ApiContact): VenueContact {
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
