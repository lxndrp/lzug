import type {
  ExamRoom,
  ExamVenue,
  ExamVenueContact,
  VenueChangeImpact,
} from './master-data.models';
import { Injectable, inject } from '@angular/core';

import { ApiClient } from './api-client.service';

/** Exam-venue, room, contact, promotion, and consequence operations. */

@Injectable({ providedIn: 'root' })
export class VenueApiService {
  private readonly client = inject(ApiClient);
  createExamVenue(payload: Record<string, unknown>) {
    return this.client.post<ExamVenue>('/api/exam-venues', payload);
  }

  checkExamVenueDuplicates(payload: Record<string, unknown>, excludedId?: number) {
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

  updateExamVenue(id: number, payload: Record<string, unknown> & { expected_revision: number }) {
    return this.client.patch<ExamVenue>(`/api/exam-venues/${id}`, payload);
  }

  geocodeExamVenue(id: number, expectedRevision: number) {
    return this.client.post<{ latitude: number; longitude: number; source: string }>(
      `/api/exam-venues/${id}/geocode`,
      { expected_revision: expectedRevision },
    );
  }

  deleteExamVenue(id: number, expectedRevision: number) {
    return this.client.delete<void>(`/api/exam-venues/${id}`, {
      body: { expected_revision: expectedRevision },
    });
  }

  createExamRoom(venueId: number, payload: Record<string, unknown>) {
    return this.client.post<ExamRoom>(`/api/exam-venues/${venueId}/rooms`, payload);
  }

  updateExamRoom(id: number, payload: Record<string, unknown> & { expected_revision: number }) {
    return this.client.patch<ExamRoom>(`/api/exam-rooms/${id}`, payload);
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
      body: { expected_revision: expectedRevision },
    });
  }

  createExamVenueContact(venueId: number, payload: Record<string, unknown>) {
    return this.client.post<ExamVenueContact>(`/api/exam-venues/${venueId}/contacts`, payload);
  }

  updateExamVenueContact(
    id: number,
    payload: Record<string, unknown> & { expected_revision: number },
  ) {
    return this.client.patch<ExamVenueContact>(`/api/exam-venue-contacts/${id}`, payload);
  }

  deleteExamVenueContact(id: number, expectedRevision: number) {
    return this.client.delete<void>(`/api/exam-venue-contacts/${id}`, {
      body: { expected_revision: expectedRevision },
    });
  }

  requestExamVenuePromotion(id: number, expectedRevision: number, reason: string) {
    return this.client.post(`/api/exam-venues/${id}/promotion-requests`, {
      expected_revision: expectedRevision,
      reason,
    });
  }

  decideExamVenuePromotion(
    id: number,
    expectedRevision: number,
    decision: 'approve' | 'reject',
    reason: string,
  ) {
    return this.client.post<ExamVenue>(`/api/exam-venue-promotion-requests/${id}/decision`, {
      expected_revision: expectedRevision,
      decision,
      reason,
    });
  }
}
