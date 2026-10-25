import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import type { ApplicationShellContextPort } from '../shell/application-shell-context.port';
import { PlanningApiService } from './planning-api.service';

/** HTTP adapter for the shell's small, independent context summary. */
@Injectable({ providedIn: 'root' })
export class HttpApplicationShellContextAdapter implements ApplicationShellContextPort {
  private readonly api = inject(PlanningApiService);

  load(roundId: number) {
    return this.api.loadShellContext(roundId).pipe(
      map(({ root, round, summary, halfYear }) => {
        return {
          applicationVersion: root.version,
          roundId,
          halfYear: `${halfYear.season === 'summer' ? 'Sommer' : 'Winter'} ${halfYear.year}`,
          round: round.name,
          committee: summary.round.committee_name,
          status: round.status,
        };
      }),
    );
  }
}
