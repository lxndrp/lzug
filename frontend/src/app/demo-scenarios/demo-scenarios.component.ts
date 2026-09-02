import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { TuiButton, TuiNotification } from '@taiga-ui/core';
import { finalize, interval } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { DemoRole, DemoScenario, DemoScenarioOverview } from '../api/api.models';
import { PlanningApiService } from '../api/planning-api.service';
import { AuthService } from '../auth/auth.service';

@Component({
  selector: 'app-demo-scenarios',
  imports: [TuiButton, TuiNotification],
  templateUrl: './demo-scenarios.component.html',
  styleUrl: './demo-scenarios.component.css',
})
export class DemoScenariosComponent implements OnInit {
  private readonly api = inject(PlanningApiService);
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly router = inject(Router);

  protected readonly overview = signal<DemoScenarioOverview | null>(null);
  protected readonly remainingSeconds = signal(0);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly timeRemaining = computed(() => {
    const seconds = Math.max(0, this.remainingSeconds());
    const minutes = Math.floor(seconds / 60);
    return `${minutes}:${String(seconds % 60).padStart(2, '0')}`;
  });

  constructor() {
    interval(1000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.remainingSeconds.update((seconds) => Math.max(0, seconds - 1));
        if (this.remainingSeconds() === 0 && this.overview()) this.auth.markAnonymous();
      });
  }

  ngOnInit(): void {
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api
      .getDemoScenarios()
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (overview) => this.setOverview(overview),
        error: () => this.error.set('Der Demo-Arbeitsstand konnte nicht geladen werden.'),
      });
  }

  protected switchRole(role: DemoRole): void {
    if (this.busy() || role === this.overview()?.current_role) return;
    this.busy.set(true);
    this.error.set(null);
    this.auth
      .startDemoSession(role)
      .pipe(finalize(() => this.busy.set(false)))
      .subscribe({
        next: () => this.load(),
        error: () => this.error.set('Die Demo-Rolle konnte nicht gewechselt werden.'),
      });
  }

  protected restart(): void {
    if (this.busy()) return;
    if (
      !window.confirm(
        'Alle Änderungen, Benachrichtigungen und Kalenderfolgen dieses Demo-Arbeitsstands verwerfen?',
      )
    ) {
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    this.api
      .resetDemoScenarios()
      .pipe(finalize(() => this.busy.set(false)))
      .subscribe({
        next: () => this.load(),
        error: () => this.error.set('Die Demo-Szenarien konnten nicht neu gestartet werden.'),
      });
  }

  protected leave(): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.auth
      .logout()
      .pipe(finalize(() => this.busy.set(false)))
      .subscribe({
        error: () => this.error.set('Die Demo-Sitzung konnte nicht beendet werden.'),
      });
  }

  protected openScenario(scenario: DemoScenario, event: Event): void {
    event.preventDefault();
    if (scenario.next_role !== this.overview()?.current_role && scenario.status !== 'complete') {
      return;
    }
    void this.router.navigateByUrl(scenario.path);
  }

  protected roleLabel(role: DemoRole): string {
    return {
      chair: 'Vorsitz',
      examiner: 'Eingeplanter Prüfer',
      replacement: 'Angefragter Ersatzprüfer',
    }[role];
  }

  protected roleDisplayName(role: DemoRole): string {
    return this.overview()?.roles.find((item) => item.name === role)?.display_name ?? '';
  }

  protected statusLabel(status: DemoScenario['status']): string {
    return { ready: 'Bereit', in_progress: 'In Bearbeitung', complete: 'Abgeschlossen' }[status];
  }

  private setOverview(overview: DemoScenarioOverview): void {
    this.overview.set(overview);
    this.remainingSeconds.set(overview.remaining_seconds);
  }
}
