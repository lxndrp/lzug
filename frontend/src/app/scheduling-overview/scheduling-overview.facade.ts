import { Injectable, inject, signal } from '@angular/core';

import { SchedulingOverviewApplication } from './application/scheduling-overview.application';
import { SchedulingOverviewItem } from './scheduling-overview.models';

export type OverviewState = 'loading' | 'ready' | 'error';

/** UI-facing state and commands for the scheduling-overview feature. */
@Injectable()
export class SchedulingOverviewFacade {
  private readonly application = inject(SchedulingOverviewApplication);
  private readonly stateValue = signal<OverviewState>('loading');
  private readonly itemsValue = signal<readonly SchedulingOverviewItem[]>([]);

  readonly state = this.stateValue.asReadonly();
  readonly items = this.itemsValue.asReadonly();

  load(): void {
    this.stateValue.set('loading');
    this.application.getOverview().subscribe({
      next: (items) => {
        this.itemsValue.set(items);
        this.stateValue.set('ready');
      },
      error: () => this.stateValue.set('error'),
    });
  }
}
