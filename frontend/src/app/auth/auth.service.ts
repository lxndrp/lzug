import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, map, of, switchMap, tap } from 'rxjs';

import { DemoRole } from '../api/api.models';
import { RuntimeExperienceService } from '../runtime/runtime-experience.service';

export type AuthState = 'checking' | 'authenticated' | 'anonymous';

export type AuthSession = {
  authenticated: boolean;
  account_id: number;
  person_id: number | null;
  committee_member_id: number | null;
  is_operator: boolean;
  demo_role?: DemoRole;
  display_name?: string;
  capabilities?: string[];
  demo_matrix_version?: string;
  demo_workspace_expires_at?: string;
};

export type AuthPreparation = {
  email: string;
  expires_at: string;
  totp_secret?: string;
};

export type AuthCompletion = {
  activated?: boolean;
  recovered?: boolean;
  account: { id: number; email: string; is_operator: boolean };
  recovery_codes: string[];
};

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly runtimeExperience = inject(RuntimeExperienceService);
  private demoExpiryTimer: ReturnType<typeof setTimeout> | null = null;

  readonly state = signal<AuthState>('checking');
  readonly session = signal<AuthSession | null>(null);

  hasCapability(capability: string): boolean {
    const capabilities = this.session()?.capabilities;
    return capabilities === undefined || capabilities.includes(capability);
  }

  initialize() {
    if (this.state() !== 'checking') return of(this.state() === 'authenticated');
    return this.http.get<AuthSession>('/api/session').pipe(
      tap((session) => {
        this.acceptSession(session);
        if (this.isAuthRoute(this.router.url)) {
          void this.router.navigateByUrl(this.entryPath(session), { replaceUrl: true });
        }
      }),
      map(() => true),
      catchError(() => {
        this.markAnonymous();
        return of(false);
      }),
    );
  }

  login(email: string, password: string, secondFactor: string) {
    return this.http
      .post<{ authenticated: true; account_id: number; expires_at: string }>('/api/auth/login', {
        email,
        password,
        second_factor: secondFactor,
      })
      .pipe(
        tap(() => {
          this.state.set('authenticated');
          void this.router.navigateByUrl('/dashboard', { replaceUrl: true });
        }),
      );
  }

  acceptAuthentication() {
    return this.http.get<AuthSession>('/api/session').pipe(
      tap((session) => {
        this.acceptSession(session);
        void this.router.navigateByUrl(this.entryPath(session), { replaceUrl: true });
      }),
    );
  }

  startDemoSession(role: DemoRole) {
    return this.runtimeExperience
      .startDemoSession(role)
      .pipe(switchMap(() => this.acceptAuthentication()));
  }

  logout() {
    return this.http.post<void>('/api/session/logout', {}).pipe(tap(() => this.markAnonymous()));
  }

  prepareInvitation(token: string) {
    return this.http.post<AuthPreparation>('/api/auth/invitation/prepare', { token });
  }

  activateInvitation(token: string, password: string, totpSecret: string, totpCode: string) {
    return this.http.post<AuthCompletion>('/api/auth/invitation/activate', {
      token,
      password,
      totp_secret: totpSecret,
      totp_code: totpCode,
    });
  }

  prepareRecovery(token: string) {
    return this.http.post<AuthPreparation>('/api/auth/recovery/prepare', { token });
  }

  completeRecovery(token: string, password: string, totpSecret: string, totpCode: string) {
    return this.http.post<AuthCompletion>('/api/auth/recovery/complete', {
      token,
      password,
      totp_secret: totpSecret,
      totp_code: totpCode,
    });
  }

  markAnonymous(): void {
    if (this.demoExpiryTimer !== null) clearTimeout(this.demoExpiryTimer);
    this.demoExpiryTimer = null;
    this.session.set(null);
    this.state.set('anonymous');
    if (!this.isAuthRoute(this.router.url)) {
      void this.router.navigateByUrl('/login', { replaceUrl: true });
    }
  }

  private isAuthRoute(url: string): boolean {
    return ['/login', '/activate', '/recover'].some((route) => url.split('?')[0] === route);
  }

  private entryPath(session: AuthSession): string {
    return session.demo_role ? '/demo-scenarios' : '/dashboard';
  }

  private acceptSession(session: AuthSession): void {
    this.session.set(session);
    this.state.set('authenticated');
    this.scheduleDemoExpiry(session);
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
