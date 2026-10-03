import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { AuthService } from '../auth/auth.service';

import { masterDataFixture } from '../testing/fixtures';
import { HttpLocationsReadAdapter } from './http-locations-read.adapter';

describe('HttpLocationsReadAdapter', () => {
  let adapter: HttpLocationsReadAdapter;
  let http: HttpTestingController;

  afterEach(() => http.verify());

  it('loads venues independently and preserves the collection capability', () => {
    TestBed.configureTestingModule({
      providers: [
        HttpLocationsReadAdapter,
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { session: () => ({ committee_member_id: null }) } },
      ],
    });
    adapter = TestBed.inject(HttpLocationsReadAdapter);
    http = TestBed.inject(HttpTestingController);
    let result: ReturnType<typeof adapter.load> extends import('rxjs').Observable<infer T>
      ? T | undefined
      : never;

    adapter.load().subscribe((snapshot) => (result = snapshot));

    const request = http.expectOne('/api/exam-venues');
    expect(request.request.method).toBe('GET');
    request.flush({
      items: masterDataFixture.examVenues,
      _links: { create: { href: '/api/exam-venues' } },
    });

    expect(result?.venues[0]).toMatchObject({
      id: masterDataFixture.examVenues[0].id,
      name: masterDataFixture.examVenues[0].name,
    });
    expect(result?.canCreateVenue).toBe(true);
    expect(result?.committees).toEqual([]);
  });

  it('keeps a venue read failure visible to the feature instead of returning empty data', () => {
    TestBed.configureTestingModule({
      providers: [
        HttpLocationsReadAdapter,
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { session: () => ({ committee_member_id: null }) } },
      ],
    });
    adapter = TestBed.inject(HttpLocationsReadAdapter);
    http = TestBed.inject(HttpTestingController);
    let failed = false;

    adapter.load().subscribe({ error: () => (failed = true) });
    http
      .expectOne('/api/exam-venues')
      .flush({ detail: 'Forbidden.' }, { status: 403, statusText: 'Forbidden' });

    expect(failed).toBe(true);
  });
});
