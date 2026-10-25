import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { masterDataFixture } from '../testing/fixtures';
import { AuthService } from '../auth/auth.service';
import type { LocationSnapshot } from '../locations/locations.models';
import type { ExamVenueResponse } from './generated/types.gen';
import { HttpLocationsReadAdapter } from './http-locations-read.adapter';

describe('HttpLocationsReadAdapter', () => {
  let adapter: HttpLocationsReadAdapter;
  let http: HttpTestingController;

  afterEach(() => http.verify());

  it('loads venues independently and preserves the collection capability', () => {
    configure();
    const results: LocationSnapshot[] = [];

    adapter.load().subscribe((snapshot) => results.push(snapshot));

    const request = http.expectOne('/api/exam-venues');
    const committees = http.expectOne('/api/committees');
    expect(request.request.method).toBe('GET');
    expect(committees.request.method).toBe('GET');
    request.flush({
      items: [venueResponse()],
      _links: { create: { href: '/api/exam-venues' } },
    });
    expect(results.at(-1)).toMatchObject({
      venues: expect.any(Array),
      committeeLoadPending: true,
    });
    committees.flush({ items: masterDataFixture.committees, _links: {} });

    expect(results.at(-1)).toMatchObject({
      venues: expect.any(Array),
      committeeLoadPending: false,
    });
    const result = results.at(-1)!;
    expect(result.venues[0]).toMatchObject({
      id: masterDataFixture.examVenues[0].id,
      name: masterDataFixture.examVenues[0].name,
      scope: 'committee',
      accessibilityStatus: 'confirmed',
      coordinateStatus: 'confirmed',
      mapProvider: { mode: 'osm' },
      capabilities: { manage: true, requestPromotion: true },
    });
    expect(result.canCreateVenue).toBe(true);
    expect(result.committees).toEqual(
      masterDataFixture.committees.map(({ id, name }) => ({ id, name })),
    );
    expect(result.committeeLoadError).toBe(false);
  });

  it('keeps a venue read failure visible to the feature instead of returning empty data', () => {
    configure();
    let failed = false;

    adapter.load().subscribe({ error: () => (failed = true) });
    http.expectOne('/api/committees').flush({ items: [], _links: {} });
    http
      .expectOne('/api/exam-venues')
      .flush({ detail: 'Forbidden.' }, { status: 403, statusText: 'Forbidden' });

    expect(failed).toBe(true);
  });

  it('keeps venues available and reports when supplementary committee names fail', () => {
    configure();
    let result: ReturnType<typeof adapter.load> extends import('rxjs').Observable<infer T>
      ? T | undefined
      : never;

    adapter.load().subscribe((snapshot) => (result = snapshot));
    http
      .expectOne('/api/committees')
      .flush({ detail: 'Forbidden.' }, { status: 403, statusText: 'Forbidden' });
    http.expectOne('/api/exam-venues').flush({
      items: [venueResponse()],
      _links: { create: { href: '/api/exam-venues' } },
    });

    expect(result?.venues).toHaveLength(masterDataFixture.examVenues.length);
    expect(result?.committees).toEqual([]);
    expect(result?.committeeLoadError).toBe(true);
  });

  it('uses venue-provided committee names for operators without requesting the member-only list', () => {
    configure(true);
    let result: LocationSnapshot | undefined;

    adapter.load().subscribe((snapshot) => (result = snapshot));

    http.expectNone('/api/committees');
    http.expectOne('/api/exam-venues').flush({
      items: [{ ...venueResponse(), committee_name: 'Hamburg' }],
      _links: {},
    });

    expect(result?.committees).toEqual([]);
    expect(result?.committeeLoadError).toBe(false);
    expect(result?.venues[0].committeeName).toBe('Hamburg');
  });

  function venueResponse() {
    const venue = masterDataFixture.examVenues[0];
    return {
      ...venue,
      _links: {},
      coordinate_source: venue.coordinate_source ?? null,
      coordinate_status: venue.coordinate_status ?? 'missing',
      latitude: venue.latitude ?? null,
      longitude: venue.longitude ?? null,
      map_provider: venue.map_provider ?? { mode: 'off' },
      created_at: '2026-10-25T10:00:00Z',
      updated_at: '2026-10-25T10:00:00Z',
      rooms: venue.rooms.map((room) => ({
        ...room,
        created_at: '2026-10-25T10:00:00Z',
        updated_at: '2026-10-25T10:00:00Z',
        _links: {},
      })),
      contacts: venue.contacts.map((contact) => ({
        ...contact,
        created_at: '2026-10-25T10:00:00Z',
        updated_at: '2026-10-25T10:00:00Z',
        _links: {},
      })),
    } satisfies ExamVenueResponse;
  }

  function configure(isOperator = false): void {
    TestBed.configureTestingModule({
      providers: [
        HttpLocationsReadAdapter,
        { provide: AuthService, useValue: { session: signal({ is_operator: isOperator }) } },
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    adapter = TestBed.inject(HttpLocationsReadAdapter);
    http = TestBed.inject(HttpTestingController);
  }
});
