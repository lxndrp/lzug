import { Injectable, inject } from '@angular/core';

import { ExamProtocolApplication } from './exam-protocol.application';

/** UI-facing operations for the exam protocol feature. */
@Injectable({ providedIn: 'root' })
export class ExamProtocolFacade {
  private readonly application = inject(ExamProtocolApplication);

  get(...args: Parameters<ExamProtocolApplication['get']>) {
    return this.application.get(...args);
  }

  update(...args: Parameters<ExamProtocolApplication['update']>) {
    return this.application.update(...args);
  }

  submit(...args: Parameters<ExamProtocolApplication['submit']>) {
    return this.application.submit(...args);
  }

  respond(...args: Parameters<ExamProtocolApplication['respond']>) {
    return this.application.respond(...args);
  }

  requestCorrection(...args: Parameters<ExamProtocolApplication['requestCorrection']>) {
    return this.application.requestCorrection(...args);
  }

  openCorrection(...args: Parameters<ExamProtocolApplication['openCorrection']>) {
    return this.application.openCorrection(...args);
  }

  export(...args: Parameters<ExamProtocolApplication['export']>) {
    return this.application.export(...args);
  }
}
