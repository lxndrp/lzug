import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subscription } from 'rxjs';

import { SchedulingOverviewApplication } from './application/scheduling-overview.application';
import { SchedulingOverviewItem } from './scheduling-overview.models';

export type OverviewState = 'loading' | 'ready' | 'error';

/** UI-facing state and commands for the scheduling-overview feature. */
@Injectable()
export class SchedulingOverviewFacade {
  private readonly application = inject(SchedulingOverviewApplication);
  private readonly destroyRef = inject(DestroyRef);
  private readonly stateValue = signal<OverviewState>('loading');
  private readonly itemsValue = signal<readonly SchedulingOverviewItem[]>([]);
  private loadGeneration = 0;
  private activeLoad?: Subscription;

  readonly state = this.stateValue.asReadonly();
  readonly items = this.itemsValue.asReadonly();

  constructor() {
    this.application.planningWritesCommitted$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.load());
  }

  load(): void {
    const generation = ++this.loadGeneration;
    this.activeLoad?.unsubscribe();
    this.stateValue.set('loading');
    this.activeLoad = this.application
      .getOverview()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (items) => {
          if (generation !== this.loadGeneration) return;
          this.itemsValue.set(items);
          this.stateValue.set('ready');
        },
        error: () => {
          if (generation === this.loadGeneration) this.stateValue.set('error');
        },
      });
  }
}
