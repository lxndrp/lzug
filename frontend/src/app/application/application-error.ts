export type ApplicationErrorKind =
  | 'invalid-request'
  | 'unauthenticated'
  | 'forbidden'
  | 'not-found'
  | 'conflict'
  | 'unavailable'
  | 'unexpected';

/** Transport-neutral failure exposed by application operations. */
export class ApplicationError extends Error {
  constructor(
    readonly kind: ApplicationErrorKind,
    message: string,
    readonly code?: string,
    readonly details?: unknown,
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = 'ApplicationError';
  }
}
