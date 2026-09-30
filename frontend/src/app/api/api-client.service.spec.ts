import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ApplicationError } from '../application/application-error';
import { ApiClient } from './api-client.service';

describe('ApiClient HTTP error boundary', () => {
  let client: ApiClient;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    client = TestBed.inject(ApiClient);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('turns an HTTP conflict into a transport-neutral application error', () => {
    let failure: unknown;
    client.get('/api/planning-proposals').subscribe({ error: (error) => (failure = error) });

    http.expectOne('/api/planning-proposals').flush(
      {
        error: {
          code: 'revision_conflict',
          message: 'Reload the latest proposal.',
          current_revision: 8,
        },
      },
      { status: 409, statusText: 'Conflict' },
    );

    expect(failure).toBeInstanceOf(ApplicationError);
    expect(failure).toMatchObject({
      kind: 'conflict',
      code: 'revision_conflict',
      message: 'Reload the latest proposal.',
      details: { current_revision: 8 },
    });
    expect(failure).not.toHaveProperty('status');
  });
});
