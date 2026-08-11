import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of, throwError } from 'rxjs';

import { routes } from '../app.routes';
import { AuthFlowComponent } from './auth-flow.component';
import { AuthService } from './auth.service';

describe('AuthFlowComponent', () => {
  let fixture: ComponentFixture<AuthFlowComponent>;
  let component: AuthFlowComponent;
  let auth: {
    login: ReturnType<typeof vi.fn>;
    prepareInvitation: ReturnType<typeof vi.fn>;
    activateInvitation: ReturnType<typeof vi.fn>;
    prepareRecovery: ReturnType<typeof vi.fn>;
    completeRecovery: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    auth = {
      login: vi.fn(),
      prepareInvitation: vi.fn(),
      activateInvitation: vi.fn(),
      prepareRecovery: vi.fn(),
      completeRecovery: vi.fn(),
    };
    await TestBed.configureTestingModule({
      imports: [AuthFlowComponent],
      providers: [{ provide: AuthService, useValue: auth }, provideRouter(routes)],
    }).compileComponents();
    fixture = TestBed.createComponent(AuthFlowComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('shows a safe error when login fails and does not expose the submitted values', () => {
    auth.login.mockReturnValue(
      throwError(() => ({ error: { error: 'Anmeldung nicht möglich.' } })),
    );
    const instance = component as unknown as {
      email: string;
      password: string;
      secondFactor: string;
      submitLogin(): void;
    };
    instance.email = 'member@example.invalid';
    instance.password = 'correct horse battery staple';
    instance.secondFactor = '123456';
    instance.submitLogin();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Anmeldung nicht möglich.');
    expect(fixture.nativeElement.textContent).not.toContain(instance.password);
    expect(fixture.nativeElement.textContent).not.toContain(instance.secondFactor);
  });

  it('supports alphanumeric recovery codes and follows auth route changes', async () => {
    const factor = (fixture.nativeElement as HTMLElement).querySelector<HTMLInputElement>(
      '#auth-factor',
    );
    expect(factor?.getAttribute('inputmode')).toBe('text');

    await TestBed.inject(Router).navigateByUrl('/activate');
    fixture.detectChanges();

    expect((component as unknown as { screen: () => string }).screen()).toBe('activate');
  });

  it('activates an invitation and displays recovery codes only after completion', () => {
    const instance = component as unknown as {
      screen: { set(value: string): void };
      token: string;
      password: string;
      passwordConfirmation: string;
      totpCode: string;
      prepare(): void;
      complete(): void;
    };
    instance.screen.set('activate');
    instance.token = 'invitation-token';
    auth.prepareInvitation.mockReturnValue(
      of({
        email: 'member@example.invalid',
        expires_at: '2026-01-01T20:00:00+00:00',
        totp_secret: 'JBSWY3DPEHPK3PXP',
      }),
    );
    instance.prepare();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('JBSWY3DPEHPK3PXP');
    expect(fixture.nativeElement.textContent).not.toContain('invitation-token');

    instance.password = 'correct horse battery staple';
    instance.passwordConfirmation = instance.password;
    instance.totpCode = '123456';
    auth.activateInvitation.mockReturnValue(
      of({
        activated: true,
        account: { id: 2, email: 'member@example.invalid', is_operator: false },
        recovery_codes: ['ABCD2345EF', 'GHJK6789MN'],
      }),
    );
    instance.complete();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('ABCD2345EF');
    expect(fixture.nativeElement.textContent).toContain('genau einmal angezeigt');
  });

  it('requires matching passwords and supports recovery re-registration', () => {
    const instance = component as unknown as {
      screen: { set(value: string): void };
      token: string;
      password: string;
      passwordConfirmation: string;
      totpCode: string;
      prepare(): void;
      complete(): void;
    };
    instance.screen.set('recover');
    instance.token = 'recovery-token';
    auth.prepareRecovery.mockReturnValue(
      of({
        email: 'member@example.invalid',
        expires_at: '2026-01-01T20:00:00+00:00',
        totp_secret: 'JBSWY3DPEHPK3PXP',
      }),
    );
    instance.prepare();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Recovery für');

    instance.password = 'first password';
    instance.passwordConfirmation = 'different password';
    instance.complete();
    expect(auth.completeRecovery).not.toHaveBeenCalled();

    instance.password = 'a new correct password';
    instance.passwordConfirmation = instance.password;
    instance.totpCode = '654321';
    auth.completeRecovery.mockReturnValue(
      of({
        recovered: true,
        account: { id: 2, email: 'member@example.invalid', is_operator: false },
        recovery_codes: ['LMNP2345QR'],
      }),
    );
    instance.complete();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('LMNP2345QR');
  });
});
