import { TestBed } from '@angular/core/testing';

import { HttpFrontendErrorReporter } from '../api/frontend-error-api.adapter';
import { FRONTEND_ERROR_REPORTER_PORT } from './frontend-error.port';
import { PrivacyPreservingErrorHandler } from './error-reporter';

describe('privacy-preserving frontend error reporting', () => {
  const report = vi.fn();

  beforeEach(() => {
    report.mockClear();
    TestBed.configureTestingModule({
      providers: [
        PrivacyPreservingErrorHandler,
        { provide: FRONTEND_ERROR_REPORTER_PORT, useValue: { report } },
      ],
    });
  });

  it('ignores ResizeObserver-loop warnings', () => {
    TestBed.inject(PrivacyPreservingErrorHandler).handleError(
      new Error('ResizeObserver loop completed with undelivered notifications.'),
    );

    expect(report).not.toHaveBeenCalled();
  });

  it('sends only a coarse runtime classification', () => {
    TestBed.inject(PrivacyPreservingErrorHandler).handleError(
      new Error('person@example.invalid token=secret request-body'),
    );

    expect(report).toHaveBeenCalledWith('runtime');
    expect(JSON.stringify(report.mock.calls)).not.toContain('person@example.invalid');
    expect(JSON.stringify(report.mock.calls)).not.toContain('secret');
  });

  it('sends only a coarse HTTP classification and status through the adapter', () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 202 }));
    vi.stubGlobal('fetch', fetchMock);

    new HttpFrontendErrorReporter().report('http', 503);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/observability/frontend-errors',
      expect.objectContaining({ body: JSON.stringify({ kind: 'http', status: 503 }) }),
    );
  });
});
