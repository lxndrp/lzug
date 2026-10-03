import { Injectable, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { finalize, Subscription } from 'rxjs';

import { SessionScopeService } from '../auth/session-scope.service';
import { LOCATIONS_READ_PORT } from './locations.port';
import { UiFeedbackService } from '../shell/ui-feedback.service';
import type { LocationSnapshot } from './locations.models';

/** Route-scoped read state for examination locations. */
@Injectable()
export class LocationsWorkspaceFacade {
  private readonly port = inject(LOCATIONS_READ_PORT);
  private readonly sessionScope = inject(SessionScopeService);
  private readonly feedback = inject(UiFeedbackService);
  private view: symbol | null = null;
  private generation = 0;
  private activeRead: Subscription | null = null;

  readonly snapshot = signal<LocationSnapshot | null>(null);
  readonly loading = signal(false);
  readonly loadError = signal(false);

  constructor() {
    this.sessionScope.changes$.pipe(takeUntilDestroyed()).subscribe(({ established }) => {
      this.generation += 1;
      this.activeRead?.unsubscribe();
      this.activeRead = null;
      this.snapshot.set(null);
      this.loading.set(false);
      this.loadError.set(false);
      if (established && this.view) this.load();
    });
  }

  activateView(view: symbol): void {
    this.view = view;
    this.load();
  }

  deactivateView(view: symbol): void {
    if (this.view !== view) return;
    this.generation += 1;
    this.activeRead?.unsubscribe();
    this.activeRead = null;
    this.view = null;
    this.snapshot.set(null);
    this.loading.set(false);
    this.loadError.set(false);
  }

  load(): void {
    if (!this.view) return;
    this.activeRead?.unsubscribe();
    const generation = ++this.generation;
    const sessionGeneration = this.sessionScope.generation();
    this.loading.set(true);
    this.loadError.set(false);
    this.activeRead = this.sessionScope
      .forCurrentSession(this.port.load())
      .pipe(
        finalize(() => {
          if (generation === this.generation) this.loading.set(false);
        }),
      )
      .subscribe({
        next: (snapshot) => {
          if (!this.isCurrent(generation, sessionGeneration)) return;
          this.snapshot.set(snapshot);
          this.loading.set(false);
        },
        error: () => {
          if (!this.isCurrent(generation, sessionGeneration)) return;
          this.loadError.set(true);
          this.feedback.notify(
            'error',
            'Prüfungsorte konnten nicht synchronisiert werden',
            'Bitte versuchen Sie die Synchronisierung erneut.',
          );
        },
      });
  }

  private isCurrent(generation: number, sessionGeneration: number): boolean {
    return generation === this.generation && sessionGeneration === this.sessionScope.generation();
  }
}
