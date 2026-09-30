import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { masterDataFixture } from '../testing/fixtures';
import { HttpLocationsAdapter } from './http-locations.adapter';
import { toLocationSnapshot } from './http-locations.mapper';

describe('HttpLocationsAdapter', () => {
  let adapter: HttpLocationsAdapter;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [HttpLocationsAdapter, provideHttpClient(), provideHttpClientTesting()],
    });
    adapter = TestBed.inject(HttpLocationsAdapter);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('maps the shared workspace venue data to link-free feature models', () => {
    const snapshot = toLocationSnapshot(masterDataFixture);
    const venue = snapshot.venues[0];

    expect(snapshot.committees[0]).toEqual({
      id: masterDataFixture.committees[0].id,
      name: masterDataFixture.committees[0].name,
    });
    expect(venue).toMatchObject({
      committeeId: expect.any(Number),
      postalCode: expect.any(String),
      isActive: true,
      mapProvider: { mode: expect.any(String) },
      capabilities: { manage: expect.any(Boolean), requestPromotion: expect.any(Boolean) },
    });
    expect(venue.rooms[0]).toMatchObject({
      venueId: venue.id,
      isActive: true,
    });
    expect(venue.contacts[0]).toMatchObject({
      venueId: venue.id,
      availabilityNotes: expect.any(String),
    });
    expect(JSON.stringify(snapshot)).not.toContain('_links');
  });

  it('maps duplicate checks, venue impact, and venue create/update commands to OpenAPI fields', () => {
    const command = {
      scope: 'committee' as const,
      committeeId: 7,
      name: 'Prüfungszentrum West',
      street: 'Testweg 2',
      postalCode: '20095',
      city: 'Hamburg',
      country: 'Deutschland',
      accessibilityStatus: 'confirmed' as const,
      isAccessible: true,
      isActive: true,
    };

    adapter
      .checkDuplicates(command, 8)
      .subscribe((duplicates) =>
        expect(duplicates).toEqual([
          { id: 9, name: 'Ähnlicher Ort', scope: 'global', address: 'Testweg 2, Hamburg' },
        ]),
      );
    const duplicateCheck = http.expectOne('/api/exam-venues/duplicate-check');
    expect(duplicateCheck.request.body).toEqual({
      name: command.name,
      street: command.street,
      postal_code: command.postalCode,
      city: command.city,
      country: command.country,
      excluded_id: 8,
    });
    duplicateCheck.flush({
      items: [{ id: 9, name: 'Ähnlicher Ort', scope: 'global', address: 'Testweg 2, Hamburg' }],
    });

    adapter
      .getVenueChangeImpact(8, { expectedRevision: 4, postalCode: '20100' })
      .subscribe((impact) => expect(impact).toEqual(changeImpact()));
    const impact = http.expectOne('/api/exam-venues/8/change-impact');
    expect(impact.request.body).toEqual({ expected_revision: 4, postal_code: '20100' });
    impact.flush(apiChangeImpact());

    adapter.createVenue({ ...command, duplicatesReviewed: true }).subscribe((venue) => {
      expect(venue.name).toBe(command.name);
      expect(venue.committeeId).toBe(7);
      expect(venue.rooms[0].roomNumber).toBe('101');
      expect(JSON.stringify(venue)).not.toContain('_links');
    });
    const create = http.expectOne('/api/exam-venues');
    expect(create.request.method).toBe('POST');
    expect(create.request.body).toMatchObject({
      scope: 'committee',
      committee_id: 7,
      postal_code: '20095',
      accessibility_status: 'confirmed',
      is_accessible: true,
      duplicates_reviewed: true,
    });
    create.flush(apiVenue());

    adapter
      .updateVenue({
        id: 8,
        payload: { expectedRevision: 5, travelDirections: 'Eingang Nord', isActive: false },
        confirmFutureAssignments: true,
        duplicatesReviewed: false,
      })
      .subscribe((venue) => expect(venue.isActive).toBe(true));
    const update = http.expectOne('/api/exam-venues/8');
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual({
      expected_revision: 5,
      travel_directions: 'Eingang Nord',
      is_active: false,
      confirm_future_assignments: true,
      duplicates_reviewed: false,
    });
    update.flush(apiVenue());
  });

  it('maps room, contact, geocoding, promotion, and consequence commands', () => {
    adapter
      .geocodeVenue(8, 3)
      .subscribe((candidate) =>
        expect(candidate).toEqual({ latitude: 53.55, longitude: 9.99, source: 'nominatim' }),
      );
    const geocode = http.expectOne('/api/exam-venues/8/geocode');
    expect(geocode.request.body).toEqual({ expected_revision: 3 });
    geocode.flush({ latitude: 53.55, longitude: 9.99, source: 'nominatim' });

    adapter
      .createRoom({
        venueId: 8,
        payload: {
          name: 'B-202',
          building: 'Haus B',
          wing: 'Ost',
          floor: '2',
          roomNumber: 'B-202',
          accessNotes: 'Stufenfrei',
          capacity: 12,
          isActive: true,
        },
      })
      .subscribe((room) => expect(room.roomNumber).toBe('B-202'));
    const roomCreate = http.expectOne('/api/exam-venues/8/rooms');
    expect(roomCreate.request.body).toEqual({
      name: 'B-202',
      building: 'Haus B',
      wing: 'Ost',
      floor: '2',
      room_number: 'B-202',
      access_notes: 'Stufenfrei',
      capacity: 12,
      is_active: true,
    });
    roomCreate.flush(apiRoom());

    adapter
      .getRoomChangeImpact(4, { expectedRevision: 6, accessNotes: 'Stufenfrei' })
      .subscribe((impact) => expect(impact.requiresConfirmation).toBe(true));
    const roomImpact = http.expectOne('/api/exam-rooms/4/change-impact');
    expect(roomImpact.request.body).toEqual({ expected_revision: 6, access_notes: 'Stufenfrei' });
    roomImpact.flush(apiChangeImpact());

    adapter
      .updateRoom({
        id: 4,
        payload: { expectedRevision: 6, roomNumber: 'B-202', isActive: false },
        confirmFutureAssignments: true,
      })
      .subscribe((room) => expect(room.isActive).toBe(true));
    const roomUpdate = http.expectOne('/api/exam-rooms/4');
    expect(roomUpdate.request.body).toEqual({
      expected_revision: 6,
      room_number: 'B-202',
      is_active: false,
      confirm_future_assignments: true,
    });
    roomUpdate.flush(apiRoom());

    adapter
      .createContact({
        venueId: 8,
        payload: {
          label: 'Empfang',
          email: null,
          phone: '+49 40 123',
          availabilityNotes: 'werktags',
          isActive: true,
        },
      })
      .subscribe((contact) => expect(contact.availabilityNotes).toBe('werktags'));
    const contactCreate = http.expectOne('/api/exam-venues/8/contacts');
    expect(contactCreate.request.body).toEqual({
      label: 'Empfang',
      email: null,
      phone: '+49 40 123',
      availability_notes: 'werktags',
      is_active: true,
    });
    contactCreate.flush(apiContact());

    adapter
      .updateContact({
        id: 2,
        payload: { expectedRevision: 7, availabilityNotes: 'nach Vereinbarung' },
      })
      .subscribe((contact) => expect(contact.revision).toBe(7));
    const contactUpdate = http.expectOne('/api/exam-venue-contacts/2');
    expect(contactUpdate.request.body).toEqual({
      expected_revision: 7,
      availability_notes: 'nach Vereinbarung',
    });
    contactUpdate.flush({ ...apiContact(), revision: 7 });

    adapter.requestPromotion(8, 3, 'Landesweit geeignet').subscribe();
    const promotion = http.expectOne('/api/exam-venues/8/promotion-requests');
    expect(promotion.request.body).toEqual({
      expected_revision: 3,
      reason: 'Landesweit geeignet',
    });
    promotion.flush({});

    adapter.retryConsequences(12).subscribe((result) =>
      expect(result).toEqual({
        auditId: 12,
        processed: 2,
        problems: 0,
        pending: 0,
        superseded: 1,
      }),
    );
    http.expectOne('/api/exam-venue-changes/12/consequences/retry').flush({
      audit_id: 12,
      processed: 2,
      problems: 0,
      pending: 0,
      superseded: 1,
    });
  });
});

function changeImpact() {
  return {
    count: 2,
    dateFrom: '2026-11-01',
    dateTo: '2026-11-30',
    requiresConfirmation: true,
    calendar: { eventCount: 1, fields: ['address'] },
    notifications: { recipientCount: 3, fields: ['address'] },
  };
}

function apiChangeImpact() {
  return {
    count: 2,
    date_from: '2026-11-01',
    date_to: '2026-11-30',
    requires_confirmation: true,
    calendar: { event_count: 1, fields: ['address'] },
    notifications: { recipient_count: 3, fields: ['address'] },
  };
}

function apiVenue() {
  const venue = masterDataFixture.examVenues[0];
  return {
    ...venue,
    id: 8,
    committee_id: 7,
    name: 'Prüfungszentrum West',
    postal_code: '20095',
    rooms: venue.rooms.map((room) => ({ ...room, room_number: '101' })),
    _links: { self: { href: '/api/exam-venues/8' } },
  };
}

function apiRoom() {
  return {
    id: 4,
    venue_id: 8,
    name: 'B-202',
    building: 'Haus B',
    wing: 'Ost',
    floor: '2',
    room_number: 'B-202',
    access_notes: 'Stufenfrei',
    capacity: 12,
    is_active: 1,
    revision: 6,
    _links: { self: { href: '/api/exam-rooms/4' } },
  };
}

function apiContact() {
  return {
    id: 2,
    venue_id: 8,
    label: 'Empfang',
    role: null,
    phone: '+49 40 123',
    email: null,
    availability_notes: 'werktags',
    is_active: 1,
    revision: 5,
    room_ids: [],
    _links: { self: { href: '/api/exam-venue-contacts/2' } },
  };
}
