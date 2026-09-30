import { Injectable, inject } from '@angular/core';

import { EXAM_HALF_YEARS_PORT } from './exam-half-years.port';

/** UI-facing operations for examination contexts and their committee rounds. */
@Injectable({ providedIn: 'root' })
export class ExamHalfYearsWorkflowService {
  private readonly port = inject(EXAM_HALF_YEARS_PORT);

  listHalfYears() {
    return this.port.listHalfYears();
  }

  listRounds() {
    return this.port.listRounds();
  }

  createRound(...args: Parameters<typeof this.port.createRound>) {
    return this.port.createRound(...args);
  }

  getRoundLifecycle(...args: Parameters<typeof this.port.getRoundLifecycle>) {
    return this.port.getRoundLifecycle(...args);
  }

  closeRound(...args: Parameters<typeof this.port.closeRound>) {
    return this.port.closeRound(...args);
  }

  cancelRound(...args: Parameters<typeof this.port.cancelRound>) {
    return this.port.cancelRound(...args);
  }

  reopenRound(...args: Parameters<typeof this.port.reopenRound>) {
    return this.port.reopenRound(...args);
  }

  deleteEmptyRound(...args: Parameters<typeof this.port.deleteEmptyRound>) {
    return this.port.deleteEmptyRound(...args);
  }

  setCandidateTerminalStatus(...args: Parameters<typeof this.port.setCandidateTerminalStatus>) {
    return this.port.setCandidateTerminalStatus(...args);
  }

  documentIhkStatus(...args: Parameters<typeof this.port.documentIhkStatus>) {
    return this.port.documentIhkStatus(...args);
  }

  exportLifecycle(...args: Parameters<typeof this.port.exportLifecycle>) {
    return this.port.exportLifecycle(...args);
  }
}
