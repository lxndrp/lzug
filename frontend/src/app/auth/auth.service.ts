import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, map, of, tap } from 'rxjs';

export type AuthState = 'checking' | 'authenticated' | 'anonymous';

export type AuthSession = {
  authenticated: boolean;
  account_id: number;
  person_id: number | null;
  committee_member_id: number | null;
  is_operator: boolean;
  demo_role?: 'chair' | 'examiner';
  display_name?: string;
  capabilities?: string[];
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

  readonly state = signal<AuthState>('checking');
  readonly session = signal<AuthSession | null>(null);

  initialize() {
    if (this.state() !== 'checking') return of(this.state() === 'authenticated');
    return this.http.get<AuthSession>('/api/session').pipe(
      tap((session) => {
        this.session.set(session);
        this.state.set('authenticated');
        if (this.isAuthRoute(this.router.url)) {
          void this.router.navigateByUrl('/dashboard', { replaceUrl: true });
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
        this.session.set(session);
        this.state.set('authenticated');
        void this.router.navigateByUrl('/dashboard', { replaceUrl: true });
      }),
    );
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
    this.session.set(null);
    this.state.set('anonymous');
    if (!this.isAuthRoute(this.router.url)) {
      void this.router.navigateByUrl('/login', { replaceUrl: true });
    }
  }

  private isAuthRoute(url: string): boolean {
    return ['/login', '/activate', '/recover'].some((route) => url.split('?')[0] === route);
  }
}
