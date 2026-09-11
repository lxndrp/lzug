import { DatePipe } from '@angular/common';
import { Component, ElementRef, ViewChild, afterNextRender, computed, inject } from '@angular/core';
import { LifecycleService } from './lifecycle.service';

/** Accessible public maintenance screen with a separate operator diagnosis path. */
@Component({
  selector: 'app-lifecycle-notice',
  imports: [DatePipe],
  template: `
    <main aria-labelledby="lifecycle-title">
      <section>
        <p>lzug · Prüfungsverwaltung</p>
        <h1 #heading id="lifecycle-title" tabindex="-1">{{ title() }}</h1>
        <p>{{ explanation() }}</p>
        <p>
          Die Anwendung kann derzeit nicht verwendet werden. Bitte versuchen Sie es später erneut.
        </p>
        <ng-content />
        <p role="status" aria-live="polite" aria-atomic="true">
          @if (lifecycle.checking()) {
            Status wird geprüft …
          } @else if (lifecycle.checkedAt(); as checkedAt) {
            Zuletzt geprüft: {{ checkedAt | date: 'HH:mm:ss' }}. {{ title() }}.
          }
        </p>
        <p>
          Der Status wird beim Öffnen und bei einer gemeldeten Wartung aktualisiert. Weitere
          Prüfungen starten Sie selbst. Eingaben werden nicht automatisch erneut gesendet.
        </p>
        <details>
          <summary>Hinweise für Betreiber</summary>
          <p>
            Prüfen Sie den Zustand mit <code>lzug-admin system status</code> und die Diagnose mit
            <code>lzug-admin system doctor</code> über den lokalen Adminzugang.
          </p>
          <p>
            Führen Sie nur den dort ausgewiesenen und im Betreiberhandbuch beschriebenen
            Wiederherstellungs- oder Freigabeschritt aus. Prüfen Sie eine erforderliche
            Datenaktualisierung mit
            <code>lzug-admin upgrade status</code> und geben Sie sie nach der Sicherungsprüfung mit
            <code>lzug-admin upgrade apply</code> frei.
          </p>
        </details>
      </section>
    </main>
  `,
  styles: `
    main {
      min-height: 100dvh;
      display: grid;
      place-items: center;
      padding: var(--lzug-space-6) var(--lzug-space-4);
      background: var(--lzug-role-page-canvas);
    }
    section {
      box-sizing: border-box;
      width: min(100%, var(--lzug-role-reading-max));
      min-width: 0;
      padding: clamp(1rem, 5vw, 3rem);
      border: 1px solid var(--lzug-role-border);
      border-radius: var(--lzug-role-card-radius);
      background: var(--lzug-role-card-surface);
    }
    h1 {
      margin: 0;
      font-size: clamp(1.5rem, 5vw, 2rem);
    }
    p {
      line-height: 1.6;
    }
    code {
      overflow-wrap: anywhere;
    }
    summary {
      cursor: pointer;
      padding-block: 0.75rem;
      font-weight: 600;
    }
    :focus-visible {
      outline: 3px solid var(--app-color-primary);
      outline-offset: 4px;
    }
  `,
})
export class LifecycleNoticeComponent {
  readonly lifecycle = inject(LifecycleService);
  @ViewChild('heading') private heading?: ElementRef<HTMLHeadingElement>;
  readonly title = computed(() => {
    switch (this.lifecycle.state()) {
      case 'initializing':
        return 'Anwendung wird gestartet';
      case 'maintenance':
        return 'Anwendung wird gewartet';
      case 'migration_required':
        return 'Datenaktualisierung erforderlich';
      case 'migrating':
        return 'Daten werden aktualisiert';
      case 'error':
        return 'Anwendung benötigt Unterstützung';
      case 'stopping':
      case 'stopped':
        return 'Anwendung wird beendet';
      default:
        return 'Anwendung nicht erreichbar';
    }
  });
  readonly explanation = computed(() => {
    switch (this.lifecycle.state()) {
      case 'migration_required':
        return 'Der Betreiber muss die erforderliche Datenaktualisierung prüfen.';
      case 'migrating':
        return 'Eine Datenaktualisierung läuft. Bitte warten Sie deren Abschluss ab.';
      case 'error':
        return 'Der Betreiber muss die Ursache prüfen und den Betrieb wiederherstellen.';
      case 'unreachable':
        return 'Der aktuelle Zustand konnte nicht ermittelt werden. Prüfen Sie Ihre Verbindung.';
      default:
        return 'Die Anwendung ist vorübergehend nicht einsatzbereit.';
    }
  });

  constructor() {
    afterNextRender(() => this.heading?.nativeElement.focus());
  }
}
