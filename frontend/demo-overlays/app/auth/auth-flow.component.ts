import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';

import { AuthService } from './auth.service';

type DemoRole = 'chair' | 'deputy' | 'examiner';

@Component({
  selector: 'app-auth-flow',
  template: `
    <main class="auth-page" aria-labelledby="auth-title">
      <section class="auth-card">
        <p class="auth-kicker">LZUG · flüchtige öffentliche Demo</p>
        <h1 id="auth-title">Demo-Rolle auswählen</h1>
        <p class="auth-intro">
          Erkunden Sie ausschließlich synthetische Beispieldaten. Alle Änderungen und Sitzungen
          werden spätestens beim täglichen Reset um 03:00 Uhr verworfen.
        </p>
        <div class="demo-warning" role="note">
          <strong>Keine realen personenbezogenen Daten eingeben.</strong>
          Diese Demo ist keine Self-Hosting-Referenzinstallation.
        </div>
        @if (error(); as message) {
          <p class="auth-error" role="alert">{{ message }}</p>
        }
        <div class="demo-role-grid" aria-label="Verfügbare Demo-Rollen">
          <button type="button" [disabled]="busy()" (click)="start('chair')">
            <strong>Testperson Alpha</strong>
            <span>Vorsitz · Planung und Koordination ausprobieren</span>
          </button>
          <button type="button" [disabled]="busy()" (click)="start('examiner')">
            <strong>Testperson Gamma</strong>
            <span>Prüfperson · eigene Verfügbarkeit und Anwesenheit bearbeiten</span>
          </button>
          <button type="button" [disabled]="busy()" (click)="start('deputy')">
            <strong>Testperson Beta</strong>
            <span>Stellvertretung · Vier-Augen-Bestätigung und Ergebnisprozess</span>
          </button>
        </div>
        @if (busy()) {
          <p class="auth-hint" role="status">Demo-Sitzung wird vorbereitet …</p>
        }
      </section>
    </main>
  `,
  styles: `
    :host {
      display: block;
    }

    .auth-page {
      min-height: calc(100vh - 4rem);
      display: grid;
      place-items: center;
      padding: 2rem 1rem;
      background: var(--app-surface, #f4f5f7);
    }

    .auth-card {
      width: min(100%, 42rem);
      box-sizing: border-box;
      padding: clamp(1.5rem, 5vw, 3rem);
      border: 1px solid var(--app-border, #d5d9df);
      border-radius: 1rem;
      background: var(--app-card, #fff);
      box-shadow: 0 1rem 3rem rgb(32 37 45 / 10%);
    }

    .auth-kicker {
      margin: 0 0 0.5rem;
      color: var(--app-muted, #5e6773);
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    h1 {
      margin: 0;
    }

    .auth-intro {
      margin: 0.75rem 0 1.5rem;
      line-height: 1.5;
    }

    .demo-warning {
      display: grid;
      gap: 0.25rem;
      padding: 1rem;
      border-left: 0.3rem solid #a35b00;
      background: #fff3dc;
    }

    .demo-role-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 1rem;
      margin-top: 1.5rem;
    }

    .demo-role-grid button {
      display: grid;
      gap: 0.35rem;
      min-height: 7rem;
      padding: 1rem;
      border: 1px solid #005fcc;
      border-radius: 0.6rem;
      color: #fff;
      background: #005fcc;
      font: inherit;
      text-align: left;
      cursor: pointer;
    }

    .demo-role-grid button:focus-visible {
      outline: 3px solid #002f67;
      outline-offset: 3px;
    }

    .demo-role-grid button:disabled {
      cursor: wait;
      opacity: 0.6;
    }

    .demo-role-grid span,
    .auth-hint {
      line-height: 1.4;
    }

    .auth-hint {
      color: var(--app-muted, #5e6773);
    }

    .auth-error {
      color: #a52828;
      font-weight: 650;
    }

    @media (max-width: 40rem) {
      .demo-role-grid {
        grid-template-columns: 1fr;
      }
    }
  `,
})
export class AuthFlowComponent {
  private readonly auth = inject(AuthService);
  private readonly http = inject(HttpClient);

  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);

  protected start(role: DemoRole): void {
    this.busy.set(true);
    this.error.set(null);
    this.http.post('/api/demo/session', { role }).subscribe({
      next: () => {
        this.auth.acceptAuthentication().subscribe({
          next: () => this.busy.set(false),
          error: (error) => this.fail(error),
        });
      },
      error: (error) => this.fail(error),
    });
  }

  private fail(error: { error?: { error?: string } }): void {
    this.busy.set(false);
    this.error.set(error.error?.error ?? 'Die Demo-Sitzung konnte nicht gestartet werden.');
  }
}
