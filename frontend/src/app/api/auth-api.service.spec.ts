import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { AuthApiService } from './auth-api.service';

describe('AuthApiService', () => {
  let api: AuthApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(AuthApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('maps the generated session response to an application session', () => {
    api.session().subscribe((session) => {
      expect(session).toEqual({
        account_id: 7,
        authenticated: true,
        capabilities: ['planning:read'],
        committee_member_id: 3,
        demo_matrix_version: '2026-09',
        demo_role: 'chair',
        demo_workspace_expires_at: '2026-09-30T14:00:00Z',
        display_name: 'Ada Example',
        is_operator: false,
        person_id: 11,
      });
    });

    http.expectOne({ method: 'GET', url: '/api/session' }).flush({
      account_id: 7,
      authenticated: true,
      capabilities: ['planning:read'],
      committee_member_id: 3,
      demo_matrix_version: '2026-09',
      demo_role: 'chair',
      demo_workspace_expires_at: '2026-09-30T14:00:00Z',
      display_name: 'Ada Example',
      is_operator: false,
      person_id: 11,
    });
  });

  it('sends login credentials using the authentication transport contract', () => {
    api
      .login({ email: 'ada@example.test', password: 'secret', second_factor: '123456' })
      .subscribe();

    const request = http.expectOne({ method: 'POST', url: '/api/auth/login' });
    expect(request.request.body).toEqual({
      email: 'ada@example.test',
      password: 'secret',
      second_factor: '123456',
    });
    request.flush({ authenticated: true, account_id: 7, expires_at: '2026-09-30T14:00:00Z' });
  });

  it('uses the generated token and factor contracts for invitation and recovery', () => {
    api.prepareInvitation({ token: 'invite-token' }).subscribe();
    const invitation = http.expectOne({ method: 'POST', url: '/api/auth/invitation/prepare' });
    expect(invitation.request.body).toEqual({ token: 'invite-token' });
    invitation.flush({ email: 'ada@example.test', expires_at: '2026-09-30T14:00:00Z' });

    api
      .activateInvitation({
        token: 'invite-token',
        password: 'secret',
        totp_secret: 'totp-secret',
        totp_code: '123456',
      })
      .subscribe();
    const activation = http.expectOne({ method: 'POST', url: '/api/auth/invitation/activate' });
    expect(activation.request.body).toEqual({
      token: 'invite-token',
      password: 'secret',
      totp_secret: 'totp-secret',
      totp_code: '123456',
    });
    activation.flush({
      account: { id: 7, email: 'ada@example.test', is_operator: false },
      recovery_codes: ['recovery-code'],
    });

    api.prepareRecovery({ token: 'recovery-token' }).subscribe();
    const recovery = http.expectOne({ method: 'POST', url: '/api/auth/recovery/prepare' });
    expect(recovery.request.body).toEqual({ token: 'recovery-token' });
    recovery.flush({ email: 'ada@example.test', expires_at: '2026-09-30T14:00:00Z' });

    api
      .completeRecovery({
        token: 'recovery-token',
        password: 'new-secret',
        totp_secret: 'totp-secret',
        totp_code: '654321',
      })
      .subscribe();
    const completion = http.expectOne({ method: 'POST', url: '/api/auth/recovery/complete' });
    expect(completion.request.body).toEqual({
      token: 'recovery-token',
      password: 'new-secret',
      totp_secret: 'totp-secret',
      totp_code: '654321',
    });
    completion.flush({
      account: { id: 7, email: 'ada@example.test', is_operator: false },
      recovery_codes: ['replacement-code'],
    });
  });

  it('posts logout through the authentication adapter', () => {
    api.logout().subscribe();

    const request = http.expectOne({ method: 'POST', url: '/api/session/logout' });
    expect(request.request.body).toEqual({});
    request.flush(null);
  });
});
