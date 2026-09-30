import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import { VenueApiService } from './venue-api.service';
import { toContact, toRoom, toVenue } from './http-locations.mapper';
import type {
  ExamRoomCreateRequest,
  ExamRoomUpdateRequest,
  ExamVenueContactCreateRequest,
  ExamVenueContactUpdateRequest,
  ExamVenueCreateRequest,
  ExamVenueUpdateRequest,
} from './generated/types.gen';
import type {
  VenueChangeImpact,
  VenueContactCreate,
  VenueContactUpdate,
  VenueCreate,
  VenueRoomCreate,
  VenueRoomUpdate,
  VenueUpdate,
} from '../locations/locations.models';
import type { LocationsPort } from '../locations/locations.port';

/** Maps the transport-neutral examination-locations contract to the existing HTTP/OpenAPI surface. */
@Injectable({ providedIn: 'root' })
export class HttpLocationsAdapter implements LocationsPort {
  private readonly api = inject(VenueApiService);

  checkDuplicates(payload: Partial<VenueCreate>, excludedId?: number) {
    return this.api
      .checkExamVenueDuplicates(toDuplicateRequest(payload), excludedId)
      .pipe(
        map(({ items }) =>
          items.map(({ id, name, scope, address }) => ({ id, name, scope, address })),
        ),
      );
  }

  getVenueChangeImpact(id: number, payload: Partial<VenueCreate> & { expectedRevision?: number }) {
    return this.api
      .getExamVenueChangeImpact(id, {
        ...toVenueUpdateFields(payload),
        ...(payload.expectedRevision !== undefined
          ? { expected_revision: payload.expectedRevision }
          : {}),
      })
      .pipe(map(toImpact));
  }

  getRoomChangeImpact(id: number, payload: Partial<VenueRoomUpdate['payload']>) {
    return this.api
      .getExamRoomChangeImpact(id, {
        ...toRoomFields(payload),
        ...(payload.expectedRevision !== undefined
          ? { expected_revision: payload.expectedRevision }
          : {}),
      })
      .pipe(map(toImpact));
  }

  createVenue(payload: VenueCreate & { duplicatesReviewed: boolean }) {
    return this.api.createExamVenue(toVenueCreateRequest(payload)).pipe(map(toVenue));
  }

  updateVenue(
    update: VenueUpdate & { confirmFutureAssignments: boolean; duplicatesReviewed: boolean },
  ) {
    const request: ExamVenueUpdateRequest = {
      ...toVenueUpdateFields(update.payload),
      expected_revision: update.payload.expectedRevision,
      confirm_future_assignments: update.confirmFutureAssignments,
      duplicates_reviewed: update.duplicatesReviewed,
    };
    return this.api.updateExamVenue(update.id, request).pipe(map(toVenue));
  }

  geocodeVenue(id: number, revision: number) {
    return this.api.geocodeExamVenue(id, revision);
  }

  deleteVenue(id: number, revision: number) {
    return this.api.deleteExamVenue(id, revision);
  }

  createRoom(command: VenueRoomCreate) {
    const payload = command.payload;
    const request: ExamRoomCreateRequest = {
      name: payload.name,
      building: payload.building,
      wing: payload.wing,
      floor: payload.floor,
      room_number: payload.roomNumber,
      access_notes: payload.accessNotes,
      capacity: payload.capacity,
      is_active: payload.isActive,
    };
    return this.api.createExamRoom(command.venueId, request).pipe(map(toRoom));
  }

  updateRoom(command: VenueRoomUpdate & { confirmFutureAssignments: boolean }) {
    const request: ExamRoomUpdateRequest = {
      ...toRoomFields(command.payload),
      expected_revision: command.payload.expectedRevision,
      confirm_future_assignments: command.confirmFutureAssignments,
    };
    return this.api.updateExamRoom(command.id, request).pipe(map(toRoom));
  }

  deleteRoom(id: number, revision: number) {
    return this.api.deleteExamRoom(id, revision);
  }

  retryConsequences(auditId: number) {
    return this.api.retryExamVenueConsequences(auditId).pipe(
      map(({ audit_id, processed, problems, pending, superseded }) => ({
        auditId: audit_id,
        processed,
        problems,
        pending,
        superseded,
      })),
    );
  }

  createContact(command: VenueContactCreate) {
    const payload = command.payload;
    const request: ExamVenueContactCreateRequest = {
      label: payload.label,
      email: payload.email,
      phone: payload.phone,
      availability_notes: payload.availabilityNotes,
      is_active: payload.isActive,
    };
    return this.api.createExamVenueContact(command.venueId, request).pipe(map(toContact));
  }

  updateContact(command: VenueContactUpdate) {
    const request: ExamVenueContactUpdateRequest = {
      expected_revision: command.payload.expectedRevision,
      ...(command.payload.label !== undefined ? { label: command.payload.label } : {}),
      ...(command.payload.email !== undefined ? { email: command.payload.email } : {}),
      ...(command.payload.phone !== undefined ? { phone: command.payload.phone } : {}),
      ...(command.payload.availabilityNotes !== undefined
        ? { availability_notes: command.payload.availabilityNotes }
        : {}),
      ...(command.payload.isActive !== undefined ? { is_active: command.payload.isActive } : {}),
    };
    return this.api.updateExamVenueContact(command.id, request).pipe(map(toContact));
  }

  deleteContact(id: number, revision: number) {
    return this.api.deleteExamVenueContact(id, revision);
  }

  requestPromotion(id: number, revision: number, reason: string) {
    return this.api.requestExamVenuePromotion(id, revision, reason);
  }

  decidePromotion(id: number, revision: number, decision: 'approve' | 'reject', reason: string) {
    return this.api.decideExamVenuePromotion(id, revision, decision, reason).pipe(map(toVenue));
  }
}

function toVenueCreateRequest(
  value: VenueCreate & { duplicatesReviewed?: boolean },
): ExamVenueCreateRequest {
  return {
    scope: value.scope,
    committee_id: value.committeeId,
    name: value.name,
    street: value.street,
    postal_code: value.postalCode,
    city: value.city,
    country: value.country,
    site_name: value.siteName,
    entrance: value.entrance,
    travel_directions: value.travelDirections,
    accessibility_status: value.accessibilityStatus,
    is_accessible: value.isAccessible,
    accessibility_notes: value.accessibilityNotes,
    is_active: value.isActive,
    latitude: value.latitude,
    longitude: value.longitude,
    coordinate_status: value.coordinateStatus,
    coordinate_source: value.coordinateSource,
    duplicate_reason: value.duplicateReason,
    duplicates_reviewed: value.duplicatesReviewed,
  };
}

function toDuplicateRequest(value: Partial<VenueCreate>) {
  return {
    name: value.name,
    street: value.street,
    postal_code: value.postalCode,
    city: value.city,
    country: value.country,
  };
}

function toVenueUpdateFields(value: Partial<VenueCreate>) {
  return {
    ...(value.scope !== undefined ? { scope: value.scope } : {}),
    ...(value.committeeId !== undefined ? { committee_id: value.committeeId } : {}),
    ...(value.name !== undefined ? { name: value.name } : {}),
    ...(value.street !== undefined ? { street: value.street } : {}),
    ...(value.postalCode !== undefined ? { postal_code: value.postalCode } : {}),
    ...(value.city !== undefined ? { city: value.city } : {}),
    ...(value.country !== undefined ? { country: value.country } : {}),
    ...(value.siteName !== undefined ? { site_name: value.siteName } : {}),
    ...(value.entrance !== undefined ? { entrance: value.entrance } : {}),
    ...(value.travelDirections !== undefined ? { travel_directions: value.travelDirections } : {}),
    ...(value.accessibilityStatus !== undefined
      ? { accessibility_status: value.accessibilityStatus }
      : {}),
    ...(value.isAccessible !== undefined ? { is_accessible: value.isAccessible } : {}),
    ...(value.accessibilityNotes !== undefined
      ? { accessibility_notes: value.accessibilityNotes }
      : {}),
    ...(value.isActive !== undefined ? { is_active: value.isActive } : {}),
    ...(value.latitude !== undefined ? { latitude: value.latitude } : {}),
    ...(value.longitude !== undefined ? { longitude: value.longitude } : {}),
    ...(value.coordinateStatus !== undefined ? { coordinate_status: value.coordinateStatus } : {}),
    ...(value.coordinateSource !== undefined ? { coordinate_source: value.coordinateSource } : {}),
    ...(value.duplicateReason !== undefined ? { duplicate_reason: value.duplicateReason } : {}),
    ...(value.meaningfulChange !== undefined ? { meaningful_change: value.meaningfulChange } : {}),
  };
}

function toRoomFields(value: Partial<VenueRoomUpdate['payload']>) {
  return {
    ...(value.name !== undefined ? { name: value.name } : {}),
    ...(value.building !== undefined ? { building: value.building } : {}),
    ...(value.wing !== undefined ? { wing: value.wing } : {}),
    ...(value.floor !== undefined ? { floor: value.floor } : {}),
    ...(value.roomNumber !== undefined ? { room_number: value.roomNumber } : {}),
    ...(value.accessNotes !== undefined ? { access_notes: value.accessNotes } : {}),
    ...(value.capacity !== undefined ? { capacity: value.capacity } : {}),
    ...(value.isActive !== undefined ? { is_active: value.isActive } : {}),
    ...(value.meaningfulChange !== undefined ? { meaningful_change: value.meaningfulChange } : {}),
  };
}

function toImpact(value: {
  count: number;
  date_from: string | null;
  date_to: string | null;
  requires_confirmation: boolean;
  calendar: { event_count: number; fields: string[] };
  notifications: { recipient_count: number; fields: string[] };
}): VenueChangeImpact {
  return {
    count: value.count,
    dateFrom: value.date_from,
    dateTo: value.date_to,
    requiresConfirmation: value.requires_confirmation,
    calendar: { eventCount: value.calendar.event_count, fields: value.calendar.fields },
    notifications: {
      recipientCount: value.notifications.recipient_count,
      fields: value.notifications.fields,
    },
  };
}
