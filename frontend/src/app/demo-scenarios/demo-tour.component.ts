import {
  Component,
  ElementRef,
  Injector,
  ViewChild,
  afterNextRender,
  inject,
  signal,
} from '@angular/core';
import { Router } from '@angular/router';
import { TuiButton } from '@taiga-ui/core';

const OFFERED_STORAGE_KEY = 'lzug-demo-tour-offered-v1';

@Component({
  selector: 'app-demo-tour',
  imports: [TuiButton],
  templateUrl: './demo-tour.component.html',
  styleUrl: './demo-tour.component.css',
})
export class DemoTourComponent {
  private readonly router = inject(Router);
  private readonly injector = inject(Injector);
  @ViewChild('dialog') private dialog?: ElementRef<HTMLElement>;

  protected readonly visible = signal(false);
  protected readonly offered = signal(this.wasOffered());
  protected readonly index = signal(0);
  protected readonly steps = [
    {
      title: 'Synthetische Demo',
      text: 'Dieser Arbeitsstand wird regelmäßig zurückgesetzt. Verwenden Sie keine realen Daten.',
      action: 'Weiter',
    },
    {
      title: 'Demo-Rollen',
      text: 'Wechseln Sie zwischen Vorsitz, eingeplantem Prüfer und Ersatzprüfer. Fachrechte ändern sich dadurch nicht.',
      route: '/demo-scenarios',
      action: 'Rollen ansehen',
    },
    {
      title: 'Prüfungshalbjahr und Planung',
      text: 'Die Übersicht zeigt den aktiven Prüfungskontext und den jeweils nächsten zulässigen Schritt.',
      route: '/dashboard',
      action: 'Übersicht öffnen',
    },
    {
      title: 'Prüfungstag und Abschluss',
      text: 'Die regulären Ansichten erklären Durchführung, Status und Abschluss ohne eine Sonderlogik der Tour.',
      route: '/confirmed-plans',
      action: 'Prüfungspläne öffnen',
    },
    {
      title: 'Planänderungen und Orte',
      text: 'Die Szenarien zeigen Planänderungen mit Benachrichtigungs- und Kalenderfolgen sowie Prüfungsorte und Karten.',
      route: '/demo-scenarios',
      action: 'Szenarien öffnen',
    },
  ];

  start(): void {
    this.offered.set(true);
    this.storeOffered();
    this.index.set(0);
    this.visible.set(true);
    this.focusDialogAfterRender();
  }

  skip(): void {
    this.visible.set(false);
  }

  next(): void {
    const step = this.steps[this.index()];
    if (step?.route) void this.router.navigateByUrl(step.route);
    if (this.index() === this.steps.length - 1) {
      this.skip();
      return;
    }
    this.index.update((value) => value + 1);
    this.focusDialogAfterRender();
  }

  protected step() {
    return this.steps[this.index()];
  }

  private wasOffered(): boolean {
    try {
      return globalThis.localStorage?.getItem(OFFERED_STORAGE_KEY) === 'true';
    } catch {
      return false;
    }
  }

  private storeOffered(): void {
    try {
      globalThis.localStorage?.setItem(OFFERED_STORAGE_KEY, 'true');
    } catch {
      // Browser privacy settings may reject storage; the demo remains fully usable.
    }
  }

  private focusDialogAfterRender(): void {
    afterNextRender(() => this.dialog?.nativeElement.focus(), { injector: this.injector });
  }
}
