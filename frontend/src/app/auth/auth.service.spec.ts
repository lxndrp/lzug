import { Location } from '@angular/common';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
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

    service.logout().subscribe();

    expect(api.logout).toHaveBeenCalledOnce();
    expect(service.state()).toBe('anonymous');
    expect(service.session()).toBeNull();
  });

  it('starts the selected demo role and enters the shared session', () => {
    service.startDemoSession('replacement').subscribe();

    expect(runtime.startDemoSession).toHaveBeenCalledWith('replacement');
    expect(api.session).toHaveBeenCalledOnce();
    expect(service.state()).toBe('authenticated');
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
