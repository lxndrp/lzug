import { provideHttpClient, withInterceptors, HttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom, tap } from 'rxjs';
import { vi } from 'vitest';

import { AUTHENTICATION_PORT } from '../auth/auth.models';
import { SessionScopeService } from '../auth/session-scope.service';
import { FRONTEND_ERROR_REPORTER_PORT } from '../observability/frontend-error.port';
import { LIFECYCLE_AVAILABILITY_PORT } from '../runtime/lifecycle.port';
import { withSessionCredentials } from './http-interceptors';

describe('session-scoped HTTP requests', () => {
  let http: HttpTestingController;
  let scope: SessionScopeService;
  let markAnonymous: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    markAnonymous = vi.fn(() => scope.clear());
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([withSessionCredentials])),
        provideHttpClientTesting(),
        { provide: AUTHENTICATION_PORT, useValue: { markAnonymous } },
        { provide: FRONTEND_ERROR_REPORTER_PORT, useValue: { report: vi.fn() } },
        {
          provide: LIFECYCLE_AVAILABILITY_PORT,
          useValue: {
            isReady: () => true,
            currentState: () => 'ready',
            acceptUnavailable: vi.fn(),
          },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    scope = TestBed.inject(SessionScopeService);
    scope.establish({
      authenticated: true,
      account_id: 7,
      person_id: 9,
      committee_member_id: 12,
      is_operator: false,
    });
  });

  afterEach(() => http.verify({ ignoreCancelled: true }));

  it('cancels pending responses when the session scope changes', () => {
    const response = vi.fn();
    let completed = false;
    TestBed.inject(HttpClient)
      .get('/api/candidates')
      .subscribe({
        next: response,
        complete: () => (completed = true),
      });
    const request = http.expectOne('/api/candidates');

    scope.clear();

    expect(request.cancelled).toBe(true);
    expect(response).not.toHaveBeenCalled();
    expect(completed).toBe(true);
  });

  it('keeps the session-establishment response alive as it establishes the scope', async () => {
    scope.clear();
    const pending = firstValueFrom(
      TestBed.inject(HttpClient)
        .get<{ authenticated: boolean; account_id: number }>('/api/session')
        .pipe(
          tap((session) =>
            scope.establish({
              ...session,
              person_id: 9,
              committee_member_id: 12,
              is_operator: false,
            }),
          ),
        ),
    );
    const request = http.expectOne('/api/session');
    request.flush({ authenticated: true, account_id: 7 });

    await expect(pending).resolves.toEqual({ authenticated: true, account_id: 7 });
    expect(scope.generation()).toBeGreaterThan(0);
  });

  it('invalidates other pending feature requests when a protected request returns 401', () => {
    const httpClient = TestBed.inject(HttpClient);
    const staleResponse = vi.fn();
    const unauthorized = vi.fn();
    httpClient.get('/api/candidates').subscribe(staleResponse);
    const staleRequest = http.expectOne('/api/candidates');
    httpClient.get('/api/session-protected').subscribe({ error: unauthorized });
    const unauthorizedRequest = http.expectOne('/api/session-protected');

    unauthorizedRequest.flush(
      { error: 'Authentication required.' },
      { status: 401, statusText: 'Unauthorized' },
    );

    expect(markAnonymous).toHaveBeenCalledOnce();
    expect(staleRequest.cancelled).toBe(true);
    expect(staleResponse).not.toHaveBeenCalled();
    expect(unauthorized).toHaveBeenCalledOnce();
  });
});
