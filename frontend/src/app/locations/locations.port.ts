import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import type {
  GeocodeCandidate,
  Venue,
  VenueChangeImpact,
  VenueContact,
  VenueContactCreate,
  VenueContactUpdate,
  VenueCreate,
  VenueDuplicate,
  VenueRoom,
  VenueRoomCreate,
  VenueRoomUpdate,
  VenueUpdate,
} from './locations.models';

/** Transport-independent commands used by the examination-locations feature. */
export interface LocationsPort {
  checkDuplicates(payload: Partial<VenueCreate>, excludedId?: number): Observable<VenueDuplicate[]>;
  getVenueChangeImpact(
    id: number,
    payload: Partial<VenueCreate> & { expectedRevision?: number },
  ): Observable<VenueChangeImpact>;
  getRoomChangeImpact(
    id: number,
    payload: Partial<VenueRoomUpdate['payload']>,
  ): Observable<VenueChangeImpact>;
  createVenue(payload: VenueCreate & { duplicatesReviewed: boolean }): Observable<Venue>;
  updateVenue(
    update: VenueUpdate & { confirmFutureAssignments: boolean; duplicatesReviewed: boolean },
  ): Observable<Venue>;
  geocodeVenue(id: number, revision: number): Observable<Omit<GeocodeCandidate, 'venueId'>>;
  deleteVenue(id: number, revision: number): Observable<void>;
  createRoom(command: VenueRoomCreate): Observable<VenueRoom>;
  updateRoom(
    command: VenueRoomUpdate & { confirmFutureAssignments: boolean },
  ): Observable<VenueRoom>;
  deleteRoom(id: number, revision: number): Observable<void>;
  retryConsequences(auditId: number): Observable<unknown>;
  createContact(command: VenueContactCreate): Observable<VenueContact>;
  updateContact(command: VenueContactUpdate): Observable<VenueContact>;
  deleteContact(id: number, revision: number): Observable<void>;
  requestPromotion(id: number, revision: number, reason: string): Observable<unknown>;
  decidePromotion(
    id: number,
    revision: number,
    decision: 'approve' | 'reject',
    reason: string,
  ): Observable<Venue>;
}

export const LOCATIONS_PORT = new InjectionToken<LocationsPort>('LOCATIONS_PORT');
