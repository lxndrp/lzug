import { HttpErrorResponse } from '@angular/common/http';

import { ApplicationError } from '../application/application-error';
import type { ApplicationErrorKind } from '../application/application-error';
export { ApplicationError } from '../application/application-error';

type ErrorEnvelope = {
  error?: unknown;
};

type ErrorDetail = {
  code?: unknown;
  message?: unknown;
  details?: unknown;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function kindForStatus(status: number): ApplicationErrorKind {
  if (status === 400 || status === 413 || status === 415 || status === 422) {
    return 'invalid-request';
  }
  if (status === 401) return 'unauthenticated';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not-found';
  if (status === 409) return 'conflict';
  if (status === 0 || status === 429 || status >= 500) return 'unavailable';
  return 'unexpected';
}

function detailFrom(body: unknown): ErrorDetail | undefined {
  if (!isRecord(body)) return undefined;
  const envelope = body as ErrorEnvelope;
  if (isRecord(envelope.error)) return envelope.error as ErrorDetail;
  return undefined;
}

function detailsFrom(detail: ErrorDetail | undefined): unknown {
  if (!detail) return undefined;
  if (detail.details !== undefined) return detail.details;
  const details = { ...detail } as Record<string, unknown>;
  delete details['code'];
  delete details['message'];
  delete details['details'];
  return Object.keys(details).length ? details : undefined;
}

/** Converts HTTP failures at the adapter boundary into transport-neutral errors. */
export function toApplicationError(error: unknown): ApplicationError {
  if (error instanceof ApplicationError) return error;
  if (!(error instanceof HttpErrorResponse)) {
    return new ApplicationError(
      'unexpected',
      error instanceof Error ? error.message : 'The operation could not be completed.',
      undefined,
      undefined,
      { cause: error },
    );
  }

  const detail = detailFrom(error.error);
  const nestedError = (error.error as ErrorEnvelope | null)?.error;
  const message =
    (typeof detail?.message === 'string' && detail.message) ||
    (typeof nestedError === 'string' && nestedError) ||
    '';

  return new ApplicationError(
    kindForStatus(error.status),
    message,
    typeof detail?.code === 'string' ? detail.code : undefined,
    detailsFrom(detail),
    { cause: error },
  );
}
