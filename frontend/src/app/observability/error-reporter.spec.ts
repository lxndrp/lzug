import { PrivacyPreservingErrorHandler, reportFrontendError } from './error-reporter';

describe('privacy-preserving frontend error reporting', () => {
  it('sends only a coarse runtime classification', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 202 }));
    vi.stubGlobal('fetch', fetchMock);

    new PrivacyPreservingErrorHandler().handleError(
      new Error('person@example.invalid token=secret request-body'),
    );

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/observability/frontend-errors',
      expect.objectContaining({ body: JSON.stringify({ kind: 'runtime' }) }),
    );
    expect(JSON.stringify(fetchMock.mock.calls)).not.toContain('person@example.invalid');
    expect(JSON.stringify(fetchMock.mock.calls)).not.toContain('secret');
  });

  it('reports only the HTTP status', () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 202 }));
    vi.stubGlobal('fetch', fetchMock);

    reportFrontendError('http', 503);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/observability/frontend-errors',
      expect.objectContaining({ body: JSON.stringify({ kind: 'http', status: 503 }) }),
    );
  });
});
