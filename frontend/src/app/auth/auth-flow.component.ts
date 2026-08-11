import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from './auth.service';
import type { AuthCompletion, AuthPreparation } from './auth.service';

export type AuthScreen = 'login' | 'activate' | 'recover';

@Component({
  selector: 'app-auth-flow',
  imports: [FormsModule, RouterLink],
  templateUrl: './auth-flow.component.html',
  styleUrl: './auth-flow.component.css',
})
export class AuthFlowComponent {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly preparation = signal<AuthPreparation | null>(null);
  protected readonly completion = signal<AuthCompletion | null>(null);
  protected readonly screen = signal<AuthScreen>(this.screenFromUrl(this.router.url));
  protected email = '';
  protected password = '';
  protected secondFactor = '';
  protected token = '';
  protected totpSecret = '';
  protected totpCode = '';
  protected passwordConfirmation = '';

  protected submitLogin(): void {
    this.run(() => this.auth.login(this.email, this.password, this.secondFactor));
  }

  protected prepare(): void {
    this.error.set(null);
    this.preparation.set(null);
    this.busy.set(true);
    const request =
      this.screen() === 'activate'
        ? this.auth.prepareInvitation(this.token)
        : this.auth.prepareRecovery(this.token);
    request.subscribe({
      next: (preparation) => {
        this.preparation.set(preparation);
        this.totpSecret = preparation.totp_secret ?? '';
        this.busy.set(false);
      },
      error: (error) => this.fail(error),
    });
  }

  protected complete(): void {
    if (this.password !== this.passwordConfirmation) {
      this.error.set('Die Kennwörter stimmen nicht überein.');
      return;
    }
    this.error.set(null);
    this.busy.set(true);
    const request =
      this.screen() === 'activate'
        ? this.auth.activateInvitation(this.token, this.password, this.totpSecret, this.totpCode)
        : this.auth.completeRecovery(this.token, this.password, this.totpSecret, this.totpCode);
    request.subscribe({
      next: (completion) => {
        this.completion.set(completion);
        this.busy.set(false);
      },
      error: (error) => this.fail(error),
    });
  }

  protected switchScreen(screen: AuthScreen): void {
    this.reset();
    void this.router.navigateByUrl(
      `/${screen === 'activate' ? 'activate' : screen === 'recover' ? 'recover' : 'login'}`,
    );
  }

  protected reset(): void {
    this.error.set(null);
    this.preparation.set(null);
    this.completion.set(null);
    this.busy.set(false);
    this.token = '';
    this.password = '';
    this.passwordConfirmation = '';
    this.totpSecret = '';
    this.totpCode = '';
  }

  private run(requestFactory: () => ReturnType<AuthService['login']>): void {
    this.error.set(null);
    this.busy.set(true);
    requestFactory().subscribe({
      next: () => this.busy.set(false),
      error: (error) => this.fail(error),
    });
  }

  private fail(error: { error?: { error?: string } }): void {
    this.busy.set(false);
    this.error.set(error.error?.error ?? 'Der Vorgang konnte nicht abgeschlossen werden.');
  }

  private screenFromUrl(url: string): AuthScreen {
    if (url.split('?')[0] === '/activate') return 'activate';
    if (url.split('?')[0] === '/recover') return 'recover';
    return 'login';
  }
}
