import type {
  ExamRoomResponse,
  ExamRoomCreateRequest,
  ExamRoomUpdateRequest,
  ExamVenueContactResponse,
  ExamVenueContactCreateRequest,
  ExamVenueContactUpdateRequest,
  ExamVenueCreateRequest,
  ExamVenueDuplicateCheckRequest,
  ExamVenueResponse,
  ExamVenueGeocodeResponse,
  ExamVenueGeocodeRequest,
  ExamVenuePromotionDecisionRequest,
  ExamVenuePromotionRequest,
  ExamVenueUpdateRequest,
  RevisionDeleteRequest,
} from './generated/types.gen';
import type { ExamVenue, VenueChangeImpact } from './master-data.models';
import { Injectable, inject } from '@angular/core';

import { ApiClient } from './api-client.service';

/** Exam-venue, room, contact, promotion, and consequence operations. */

@Injectable({ providedIn: 'root' })
export class VenueApiService {
  private readonly client = inject(ApiClient);
  listExamVenues() {
    return this.client.collection<ExamVenueResponse>('/api/exam-venues');
  }

  createExamVenue(payload: ExamVenueCreateRequest) {
    return this.client.post<ExamVenueResponse>('/api/exam-venues', payload);
  }

  checkExamVenueDuplicates(payload: ExamVenueDuplicateCheckRequest, excludedId?: number) {
    return this.client.post<{
      items: Array<{ id: number; name: string; scope: string; address: string }>;
    }>('/api/exam-venues/duplicate-check', { ...payload, excluded_id: excludedId });
  }

  getExamVenueChangeImpact(id: number, payload: Record<string, unknown>) {
    return this.client.post<VenueChangeImpact>(`/api/exam-venues/${id}/change-impact`, payload);
  }

  getExamRoomChangeImpact(id: number, payload: Record<string, unknown>) {
    return this.client.post<VenueChangeImpact>(`/api/exam-rooms/${id}/change-impact`, payload);
  }

  updateExamVenue(id: number, payload: ExamVenueUpdateRequest) {
    return this.client.patch<ExamVenueResponse>(`/api/exam-venues/${id}`, payload);
  }

  geocodeExamVenue(id: number, expectedRevision: number) {
    const request = { expected_revision: expectedRevision } satisfies ExamVenueGeocodeRequest;
    return this.client.post<ExamVenueGeocodeResponse>(`/api/exam-venues/${id}/geocode`, request);
  }

  deleteExamVenue(id: number, expectedRevision: number) {
    return this.client.delete<void>(`/api/exam-venues/${id}`, {
      body: { expected_revision: expectedRevision } satisfies RevisionDeleteRequest,
    });
  }

  createExamRoom(venueId: number, payload: ExamRoomCreateRequest) {
    return this.client.post<ExamRoomResponse>(`/api/exam-venues/${venueId}/rooms`, payload);
  }

  updateExamRoom(id: number, payload: ExamRoomUpdateRequest) {
    return this.client.patch<ExamRoomResponse>(`/api/exam-rooms/${id}`, payload);
  }

  retryExamVenueConsequences(auditId: number) {
    return this.client.post<{
      audit_id: number;
      processed: number;
      problems: number;
      pending: number;
      superseded: number;
    }>(`/api/exam-venue-changes/${auditId}/consequences/retry`, {});
  }

  deleteExamRoom(id: number, expectedRevision: number) {
    return this.client.delete<void>(`/api/exam-rooms/${id}`, {
      body: { expected_revision: expectedRevision } satisfies RevisionDeleteRequest,
    });
  }

  createExamVenueContact(venueId: number, payload: ExamVenueContactCreateRequest) {
    return this.client.post<ExamVenueContactResponse>(
      `/api/exam-venues/${venueId}/contacts`,
      payload,
    );
  }

  updateExamVenueContact(id: number, payload: ExamVenueContactUpdateRequest) {
    return this.client.patch<ExamVenueContactResponse>(`/api/exam-venue-contacts/${id}`, payload);
  }

  deleteExamVenueContact(id: number, expectedRevision: number) {
    return this.client.delete<void>(`/api/exam-venue-contacts/${id}`, {
      body: { expected_revision: expectedRevision } satisfies RevisionDeleteRequest,
    });
  }

  requestExamVenuePromotion(id: number, expectedRevision: number, reason: string) {
    const request = {
      expected_revision: expectedRevision,
      reason,
    } satisfies ExamVenuePromotionRequest;
    return this.client.post(`/api/exam-venues/${id}/promotion-requests`, request);
  }

  decideExamVenuePromotion(
    id: number,
    expectedRevision: number,
    decision: 'approve' | 'reject',
    reason: string,
  ) {
    const request = {
      expected_revision: expectedRevision,
      decision,
      reason,
    } satisfies ExamVenuePromotionDecisionRequest;
    return this.client.post<ExamVenue>(
      `/api/exam-venue-promotion-requests/${id}/decision`,
      request,
    );
  }
}
