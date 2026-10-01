import { Injectable, signal } from '@angular/core';
import { Observable, Subject, filter, take, takeUntil } from 'rxjs';
import type { AuthSession } from './auth.models';

/** Identifies one authenticated browser session and invalidates work from older sessions. */
@Injectable({ providedIn: 'root' })
export class SessionScopeService {
  private readonly changes = new Subject<number>();
  private identityKey: string | null = null;

  readonly generation = signal(0);
  readonly changes$ = this.changes.asObservable();

  establish(session: AuthSession): void {
    const identityKey = JSON.stringify([
      session.account_id,
      session.person_id,
      session.committee_member_id,
      session.is_operator,
      [...(session.capabilities ?? [])].sort(),
      session.demo_role,
      session.demo_matrix_version,
    ]);
    if (this.identityKey === identityKey) return;
    this.identityKey = identityKey;
    this.advance();
  }

  clear(): void {
    if (this.identityKey === null) return;
    this.identityKey = null;
    this.advance();
  }

  invalidatedAfter(generation: number): Observable<number> {
    return this.changes.pipe(
      filter((current) => current !== generation),
      take(1),
    );
  }

  forCurrentSession<T>(operation: Observable<T>): Observable<T> {
    const generation = this.generation();
    return operation.pipe(takeUntil(this.invalidatedAfter(generation)));
  }

  private advance(): void {
    const generation = this.generation() + 1;
    this.generation.set(generation);
    this.changes.next(generation);
  }
}
