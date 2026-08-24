import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { routes } from '../app.routes';
import { AuthService } from './auth.service';

describe('AuthService', () => {
  let service: AuthService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter(routes)],
    });
    service = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('initializes an authenticated session', () => {
    let authenticated = false;
    service.initialize().subscribe((value) => (authenticated = value));

    const request = http.expectOne('/api/session');
    request.flush({
      authenticated: true,
      account_id: 2,
      person_id: 4,
      committee_member_id: 7,
      is_operator: false,
    });

    expect(authenticated).toBe(true);
    expect(service.state()).toBe('authenticated');
    expect(service.session()?.committee_member_id).toBe(7);
  });

  it('falls back to the anonymous state when the session is unavailable', () => {
    let authenticated = true;
    service.initialize().subscribe((value) => (authenticated = value));
    http
      .expectOne('/api/session')
      .flush({ error: 'Authentication required.' }, { status: 401, statusText: 'Unauthorized' });

    expect(authenticated).toBe(false);
    expect(service.state()).toBe('anonymous');
    expect(service.session()).toBeNull();
  });

  it('posts login and activation/recovery requests only as request bodies', () => {
    service.login('member@example.invalid', 'a password', '123456').subscribe();
    const login = http.expectOne('/api/auth/login');
    expect(login.request.method).toBe('POST');
    expect(login.request.body).toEqual({
      email: 'member@example.invalid',
      password: 'a password',
      second_factor: '123456',
    });
    login.flush({ authenticated: true, account_id: 2, expires_at: '2026-01-01T20:00:00+00:00' });

    service.prepareInvitation('invite-token').subscribe();
    const invitationPreparation = http.expectOne('/api/auth/invitation/prepare');
    expect(invitationPreparation.request.body).toEqual({ token: 'invite-token' });
    invitationPreparation.flush({
      email: 'member@example.invalid',
      expires_at: '2026-01-01T20:00:00+00:00',
      totp_secret: 'JBSWY3DPEHPK3PXP',
    });

    service
      .activateInvitation('invite-token', 'a password', 'JBSWY3DPEHPK3PXP', '123456')
      .subscribe();
    const activation = http.expectOne('/api/auth/invitation/activate');
    expect(activation.request.body).toEqual({
      token: 'invite-token',
      password: 'a password',
      totp_secret: 'JBSWY3DPEHPK3PXP',
      totp_code: '123456',
    });
    activation.flush({
      activated: true,
      account: { id: 2, email: 'member@example.invalid', is_operator: false },
      recovery_codes: ['ABCD2345EF'],
    });

    service.prepareRecovery('recovery-token').subscribe();
    const recoveryPreparation = http.expectOne('/api/auth/recovery/prepare');
    expect(recoveryPreparation.request.body).toEqual({ token: 'recovery-token' });
    recoveryPreparation.flush({
      email: 'member@example.invalid',
      expires_at: '2026-01-01T20:00:00+00:00',
      totp_secret: 'JBSWY3DPEHPK3PXP',
    });

    service
      .completeRecovery('recovery-token', 'a new password', 'JBSWY3DPEHPK3PXP', '654321')
      .subscribe();
    const recovery = http.expectOne('/api/auth/recovery/complete');
    expect(recovery.request.body).toEqual({
      token: 'recovery-token',
      password: 'a new password',
      totp_secret: 'JBSWY3DPEHPK3PXP',
      totp_code: '654321',
    });
    recovery.flush({
      recovered: true,
      account: { id: 2, email: 'member@example.invalid', is_operator: false },
      recovery_codes: ['GHJK6789MN'],
    });
  });

  it('ends the current session before returning to authentication', () => {
    service.state.set('authenticated');
    service.session.set({
      authenticated: true,
      account_id: 2,
      person_id: 3,
      committee_member_id: 3,
      is_operator: false,
      demo_role: 'examiner',
      display_name: 'Testperson Gamma',
      capabilities: ['attendance:write-own', 'availability:write-own'],
    });

    service.logout().subscribe();
    const request = http.expectOne('/api/session/logout');
    expect(request.request.method).toBe('POST');
    request.flush(null);

    expect(service.state()).toBe('anonymous');
    expect(service.session()).toBeNull();
  });
});
