import { Location } from '@angular/common';
import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, map, of, switchMap, tap, throwError } from 'rxjs';

import type { DemoRole } from '../api/api.models';
import { ApplicationError } from '../api/application-error';
import { AuthApiService } from '../api/auth-api.service';
import { RuntimeExperienceService } from '../runtime/runtime-experience.service';
import { SessionScopeService } from './session-scope.service';
import type { AuthenticationPort, AuthSession, AuthState } from './auth.models';

export type { AuthCompletion, AuthPreparation, AuthSession, AuthState } from './auth.models';

const sessionRevocationMarker = 'lzug.auth.session-revocation-pending';

function hasPendingSessionRevocation(): boolean {
  try {
    return globalThis.localStorage?.getItem(sessionRevocationMarker) === 'true';
  } catch {
    return false;
  }
}

function persistSessionRevocationPending(pending: boolean): void {
  try {
    if (pending) globalThis.localStorage?.setItem(sessionRevocationMarker, 'true');
    else globalThis.localStorage?.removeItem(sessionRevocationMarker);
  } catch {
    // Keep the in-memory fail-closed state when browser storage is unavailable.
  }
}

@Injectable({ providedIn: 'root' })
export class AuthService implements AuthenticationPort {
  private readonly api = inject(AuthApiService);
  private readonly location = inject(Location);
  private readonly router = inject(Router);
  private readonly runtimeExperience = inject(RuntimeExperienceService);
  private readonly sessionScope = inject(SessionScopeService);
  private demoExpiryTimer: ReturnType<typeof setTimeout> | null = null;

  readonly state = signal<AuthState>('checking');
  readonly session = signal<AuthSession | null>(null);
  readonly sessionRevocationPending = signal(hasPendingSessionRevocation());

  hasCapability(capability: string): boolean {
    const capabilities = this.session()?.capabilities;
    return capabilities == null || capabilities.includes(capability);
  }

  initialize() {
    if (this.sessionRevocationPending()) return of(false);
    if (this.state() !== 'checking') return of(this.state() === 'authenticated');
    return this.api.session().pipe(
      tap((session) => {
        this.acceptSession(session);
        if (this.isAuthRoute(this.currentUrl())) {
          void this.router.navigateByUrl(this.entryPath(session), { replaceUrl: true });
        }
      }),
      map(() => true),
      catchError((error: ApplicationError) => {
        if (error.code !== 'runtime_not_ready') this.markAnonymous();
        return of(false);
      }),
    );
  }

  login(email: string, password: string, secondFactor: string) {
    return this.api.login({ email, password, second_factor: secondFactor }).pipe(
      switchMap(() =>
        this.api.session().pipe(
          tap((session) => this.acceptSession(session)),
          catchError((error: unknown) => this.revokeUnvalidatedSession(error)),
        ),
      ),
      tap((session) => {
        void this.router.navigateByUrl(this.entryPath(session), { replaceUrl: true });
      }),
    );
  }

  acceptAuthentication() {
    return this.api.session().pipe(
      tap((session) => {
        this.acceptSession(session);
        void this.router.navigateByUrl(this.entryPath(session), { replaceUrl: true });
      }),
      catchError((error: unknown) => {
        this.markAnonymous();
        return throwError(() => error);
      }),
    );
  }

  retrySessionRevocation() {
    if (!this.sessionRevocationPending()) return of(false);
    return this.api.logout().pipe(
      tap(() => {
        this.sessionRevocationPending.set(false);
        persistSessionRevocationPending(false);
        this.markAnonymous();
      }),
      map(() => true),
      catchError(() => of(false)),
    );
  }

  startDemoSession(role: DemoRole) {
    return this.runtimeExperience
      .startDemoSession(role)
      .pipe(switchMap(() => this.acceptAuthentication()));
  }

  logout() {
    return this.api.logout().pipe(tap(() => this.markAnonymous()));
  }

  prepareInvitation(token: string) {
    return this.api.prepareInvitation({ token });
  }

  activateInvitation(token: string, password: string, totpSecret: string, totpCode: string) {
    return this.api.activateInvitation({
      token,
      password,
      totp_secret: totpSecret,
      totp_code: totpCode,
    });
  }

  prepareRecovery(token: string) {
    return this.api.prepareRecovery({ token });
  }

  completeRecovery(token: string, password: string, totpSecret: string, totpCode: string) {
    return this.api.completeRecovery({
      token,
      password,
      totp_secret: totpSecret,
      totp_code: totpCode,
    });
  }

  markAnonymous(): void {
    this.sessionRevocationPending.set(false);
    persistSessionRevocationPending(false);
    if (this.demoExpiryTimer !== null) clearTimeout(this.demoExpiryTimer);
    this.demoExpiryTimer = null;
    this.sessionScope.clear();
    this.session.set(null);
    this.state.set('anonymous');
    if (!this.isAuthRoute(this.currentUrl())) {
      void this.router.navigateByUrl('/login', { replaceUrl: true });
    }
  }

  private currentUrl(): string {
    return this.router.url === '/' ? this.location.path(true) || '/' : this.router.url;
  }

  private isAuthRoute(url: string): boolean {
    return ['/login', '/activate', '/recover'].some((route) => url.split('?')[0] === route);
  }

  private entryPath(session: AuthSession): string {
    return session.demo_role ? '/demo-scenarios' : '/dashboard';
  }

  private acceptSession(session: AuthSession): void {
    if (
      !session.authenticated ||
      !Number.isSafeInteger(session.account_id) ||
      session.account_id < 1
    ) {
      throw new ApplicationError('unauthenticated', 'No authenticated session was returned.');
    }
    this.sessionScope.establish(session);
    this.session.set(session);
    this.state.set('authenticated');
    this.scheduleDemoExpiry(session);
  }

  private revokeUnvalidatedSession(error: unknown) {
    this.holdUnverifiedSession();
    return this.api.logout().pipe(
      tap(() => {
        this.sessionRevocationPending.set(false);
        persistSessionRevocationPending(false);
        this.markAnonymous();
      }),
      catchError((revocationError: unknown) => {
        this.sessionRevocationPending.set(true);
        persistSessionRevocationPending(true);
        return throwError(
          () =>
            new ApplicationError(
              'unavailable',
              'Die Sitzung konnte nicht sicher beendet werden. Bitte versuchen Sie es erneut.',
              undefined,
              undefined,
              { cause: revocationError },
            ),
        );
      }),
      switchMap(() => throwError(() => error)),
    );
  }

  private holdUnverifiedSession(): void {
    if (this.demoExpiryTimer !== null) clearTimeout(this.demoExpiryTimer);
    this.demoExpiryTimer = null;
    this.sessionScope.clear();
    this.session.set(null);
    this.state.set('checking');
    this.sessionRevocationPending.set(true);
    persistSessionRevocationPending(true);
  }

  private scheduleDemoExpiry(session: AuthSession): void {
    if (this.demoExpiryTimer !== null) clearTimeout(this.demoExpiryTimer);
    this.demoExpiryTimer = null;
    if (!session.demo_workspace_expires_at) return;
    const expiry = Date.parse(session.demo_workspace_expires_at);
    const remaining = expiry - Date.now();
    if (!Number.isFinite(expiry) || remaining <= 0) {
      this.markAnonymous();
      return;
    }
    this.demoExpiryTimer = setTimeout(() => {
      if (this.session()?.demo_workspace_expires_at === session.demo_workspace_expires_at) {
        this.markAnonymous();
      }
    }, remaining);
  }
}
