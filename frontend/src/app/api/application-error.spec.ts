import { HttpErrorResponse } from '@angular/common/http';

import { ApplicationError } from '../application/application-error';
import { toApplicationError } from './application-error';

describe('HTTP error translation', () => {
  it('maps a revision conflict to an application error with backend details', () => {
    const error = toApplicationError(
      new HttpErrorResponse({
        status: 409,
        statusText: 'Conflict',
        error: {
          error: {
            code: 'revision_conflict',
            message: 'Reload the current revision.',
            details: { current_revision: 8 },
          },
        },
      }),
    );

    expect(error).toBeInstanceOf(ApplicationError);
    expect(error.kind).toBe('conflict');
    expect(error.code).toBe('revision_conflict');
    expect(error.message).toBe('Reload the current revision.');
    expect(error.details).toEqual({ current_revision: 8 });
    expect('status' in error).toBe(false);
  });

  it.each([
    [400, 'invalid-request'],
    [401, 'unauthenticated'],
    [403, 'forbidden'],
    [404, 'not-found'],
    [422, 'invalid-request'],
    [503, 'unavailable'],
    [0, 'unavailable'],
  ] as const)('maps HTTP status %s to %s', (status, kind) => {
    expect(toApplicationError(new HttpErrorResponse({ status })).kind).toBe(kind);
  });

  it('retains a backend string error as the user-facing message', () => {
    const error = toApplicationError(
      new HttpErrorResponse({ status: 400, error: { error: 'Ungültige Auswahl.' } }),
    );

    expect(error.kind).toBe('invalid-request');
    expect(error.message).toBe('Ungültige Auswahl.');
  });

  it('does not expose Angular transport messages when the backend supplies no message', () => {
    const error = toApplicationError(
      new HttpErrorResponse({ status: 503, statusText: 'Unavailable', url: '/api/session' }),
    );

    expect(error.message).toBe('The operation could not be completed.');
    expect(error.message).not.toContain('/api/session');
  });
});
