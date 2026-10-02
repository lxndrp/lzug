import { Location } from '@angular/common';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, Subject, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ApplicationError } from '../api/application-error';
import { AuthApiService } from '../api/auth-api.service';
import { RuntimeExperienceService } from '../runtime/runtime-experience.service';
import { AuthService } from './auth.service';
import type { AuthSession } from './auth.models';

const session: AuthSession = {
  authenticated: true,
  account_id: 2,
  person_id: 4,
  committee_member_id: 7,
  is_operator: false,
};

describe('AuthService', () => {
  let service: AuthService;
  let api: {
    session: ReturnType<typeof vi.fn>;
    login: ReturnType<typeof vi.fn>;
    logout: ReturnType<typeof vi.fn>;
    prepareInvitation: ReturnType<typeof vi.fn>;
    activateInvitation: ReturnType<typeof vi.fn>;
    prepareRecovery: ReturnType<typeof vi.fn>;
    completeRecovery: ReturnType<typeof vi.fn>;
  };
  let runtime: { startDemoSession: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    api = {
      session: vi.fn(() => of(session)),
      login: vi.fn(() => of({ authenticated: true as const, account_id: 2, expires_at: '' })),
      logout: vi.fn(() => of(void 0)),
      prepareInvitation: vi.fn(() => of({ email: '', expires_at: '' })),
      activateInvitation: vi.fn(() =>
        of({ account: { id: 2, email: '', is_operator: false }, recovery_codes: [] }),
      ),
      prepareRecovery: vi.fn(() => of({ email: '', expires_at: '' })),
      completeRecovery: vi.fn(() =>
        of({ account: { id: 2, email: '', is_operator: false }, recovery_codes: [] }),
      ),
    };
    runtime = { startDemoSession: vi.fn(() => of(void 0)) };
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: AuthApiService, useValue: api },
        { provide: RuntimeExperienceService, useValue: runtime },
      ],
    });
    service = TestBed.inject(AuthService);
  });

  afterEach(() => {
    service.markAnonymous();
    vi.useRealTimers();
  });

  it('initializes from a transport-neutral session', () => {
    let authenticated = false;
    service.initialize().subscribe((value) => (authenticated = value));

    expect(authenticated).toBe(true);
    expect(service.state()).toBe('authenticated');
    expect(service.session()?.committee_member_id).toBe(7);
    expect(api.session).toHaveBeenCalledOnce();
  });

  it('falls back to the anonymous state when no session exists', () => {
    api.session.mockReturnValue(throwError(() => new ApplicationError('unauthenticated', '')));
    let authenticated = true;

    service.initialize().subscribe((value) => (authenticated = value));

    expect(authenticated).toBe(false);
    expect(service.state()).toBe('anonymous');
    expect(service.session()).toBeNull();
  });

  it('preserves an authentication deep link while initialization is pending', () => {
    TestBed.inject(Location).go('/activate');
    api.session.mockReturnValue(throwError(() => new ApplicationError('unauthenticated', '')));

    service.initialize().subscribe();

    expect(TestBed.inject(Location).path()).toBe('/activate');
  });

  it('uses explicit demo capabilities while preserving product sessions', () => {
    expect(service.hasCapability('candidate-days:create')).toBe(true);

    service.session.set({
      ...session,
      demo_role: 'chair',
      capabilities: ['candidate-days:generate'],
    });

    expect(service.hasCapability('candidate-days:generate')).toBe(true);
    expect(service.hasCapability('candidate-days:create')).toBe(false);
  });

  it('delegates authentication requests and returns to the anonymous state on logout', () => {
    service.login('member@example.invalid', 'a password', '123456').subscribe();
    expect(api.login).toHaveBeenCalledWith({
      email: 'member@example.invalid',
      password: 'a password',
      second_factor: '123456',
    });
    expect(service.state()).toBe('authenticated');
    expect(service.session()?.committee_member_id).toBe(7);

    service.logout().subscribe();

    expect(api.logout).toHaveBeenCalledOnce();
    expect(service.state()).toBe('anonymous');
    expect(service.session()).toBeNull();
  });

  it('does not publish an authenticated state until the session response is validated', () => {
    service.markAnonymous();
    const sessionResponse = new Subject<AuthSession>();
    api.session.mockReturnValue(sessionResponse);

    let completed = false;
    service.login('member@example.invalid', 'a password', '123456').subscribe(() => {
      completed = true;
    });

    expect(service.state()).toBe('anonymous');
    expect(service.session()).toBeNull();
    expect(completed).toBe(false);

    sessionResponse.next(session);

    expect(service.state()).toBe('authenticated');
    expect(service.session()).toEqual(session);
    expect(completed).toBe(true);
  });

  it('rejects a successful login response without an authenticated session', () => {
    service.markAnonymous();
    api.session.mockReturnValue(of({ ...session, authenticated: false }));
    let error: unknown;

    service.login('member@example.invalid', 'a password', '123456').subscribe({
      error: (value) => (error = value),
    });

    expect(error).toBeInstanceOf(ApplicationError);
    expect(service.state()).toBe('anonymous');
    expect(service.session()).toBeNull();
  });

  it('revokes a login when the resulting session cannot be validated', () => {
    service.markAnonymous();
    const validationError = new ApplicationError('unavailable', 'Session validation failed.');
    api.session.mockReturnValue(throwError(() => validationError));
    let receivedError: unknown;

    service.login('member@example.invalid', 'a password', '123456').subscribe({
      error: (error) => (receivedError = error),
    });

    expect(api.logout).toHaveBeenCalledOnce();
    expect(receivedError).toBe(validationError);
    expect(service.state()).toBe('anonymous');
    expect(service.session()).toBeNull();
  });

  it('keeps authentication indeterminate until a failed revocation can be retried', () => {
    service.markAnonymous();
    const validationError = new ApplicationError('unavailable', 'Session validation failed.');
    api.session.mockReturnValue(throwError(() => validationError));
    api.logout.mockReturnValue(throwError(() => new ApplicationError('unavailable', 'offline')));
    let receivedError: unknown;

    service.login('member@example.invalid', 'a password', '123456').subscribe({
      error: (error) => (receivedError = error),
    });

    expect(api.logout).toHaveBeenCalledOnce();
    expect(receivedError).toBeInstanceOf(ApplicationError);
    expect((receivedError as ApplicationError).message).toContain('nicht sicher beendet');
    expect(service.state()).toBe('checking');
    expect(service.session()).toBeNull();
    expect(service.sessionRevocationPending()).toBe(true);
    expect(localStorage.getItem('lzug.auth.session-revocation-pending')).toBe('true');

    service.initialize().subscribe();
    expect(api.session).toHaveBeenCalledOnce();

    api.logout.mockReturnValue(of(void 0));
    let revoked = false;
    service.retrySessionRevocation().subscribe((result) => (revoked = result));

    expect(revoked).toBe(true);
    expect(service.state()).toBe('anonymous');
    expect(service.sessionRevocationPending()).toBe(false);
    expect(localStorage.getItem('lzug.auth.session-revocation-pending')).toBeNull();
  });

  it('starts the selected demo role and enters the shared session', () => {
    service.startDemoSession('replacement').subscribe();

    expect(runtime.startDemoSession).toHaveBeenCalledWith('replacement');
    expect(api.session).toHaveBeenCalledOnce();
    expect(service.state()).toBe('authenticated');
  });

  it('revokes a demo role when the resulting session cannot be validated', () => {
    service.initialize().subscribe();
    const validationError = new ApplicationError('unavailable', 'Session validation failed.');
    api.session.mockReturnValue(throwError(() => validationError));
    api.logout.mockReturnValue(throwError(() => new ApplicationError('unavailable', 'offline')));
    let receivedError: unknown;

    service.startDemoSession('chair').subscribe({
      error: (error) => (receivedError = error),
    });

    expect(runtime.startDemoSession).toHaveBeenCalledWith('chair');
    expect(api.session).toHaveBeenCalledTimes(2);
    expect(api.logout).toHaveBeenCalledOnce();
    expect(receivedError).toBeInstanceOf(ApplicationError);
    expect((receivedError as ApplicationError).message).toContain('nicht sicher beendet');
    expect(service.state()).toBe('checking');
    expect(service.session()).toBeNull();
    expect(service.sessionRevocationPending()).toBe(true);

    service.initialize().subscribe();

    expect(api.session).toHaveBeenCalledTimes(2);
    expect(service.state()).toBe('checking');
  });

  it('ends a demo session at its absolute workspace expiry', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-02T10:00:00Z'));
    api.session.mockReturnValue(
      of({ ...session, demo_role: 'examiner', demo_workspace_expires_at: '2026-09-02T10:00:01Z' }),
    );

    service.acceptAuthentication().subscribe();
    vi.advanceTimersByTime(999);
    expect(service.state()).toBe('authenticated');
    vi.advanceTimersByTime(1);
    expect(service.state()).toBe('anonymous');
    expect(service.session()).toBeNull();
  });
});
