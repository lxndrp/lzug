import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import type { ApplicationShellContextPort } from '../shell/application-shell-context.port';
import { withoutHttpLinks } from '../application/without-http-links';
import { PlanningApiService } from './planning-api.service';

/** HTTP adapter for the shell's small, independent context summary. */
@Injectable({ providedIn: 'root' })
export class HttpApplicationShellContextAdapter implements ApplicationShellContextPort {
  private readonly api = inject(PlanningApiService);

  load(roundId: number) {
    return this.api.loadShellContext(roundId).pipe(
      map(({ root, round, summary, halfYear }) => {
        const examRound = withoutHttpLinks(round);
        const selectedHalfYear = withoutHttpLinks(halfYear);
        const roundSummary = withoutHttpLinks(summary);
        return {
          applicationVersion: root.version,
          roundId,
          halfYear: `${selectedHalfYear.season === 'summer' ? 'Sommer' : 'Winter'} ${selectedHalfYear.year}`,
          round: examRound.name,
          committee: roundSummary.round.committee_name,
          status: examRound.status,
        };
      }),
    );
  }
}
