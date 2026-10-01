import { Injectable, inject } from '@angular/core';

import { EXAM_RESULT_PORT } from './exam-result.port';

/** Application operations for assessment, determination, communication, and retention. */
@Injectable({ providedIn: 'root' })
export class ExamResultApplication {
  private readonly port = inject(EXAM_RESULT_PORT);

  get(...args: Parameters<typeof this.port.get>) {
    return this.port.get(...args);
  }

  saveIndividualAssessment(...args: Parameters<typeof this.port.saveIndividualAssessment>) {
    return this.port.saveIndividualAssessment(...args);
  }

  withdrawIndividualAssessment(...args: Parameters<typeof this.port.withdrawIndividualAssessment>) {
    return this.port.withdrawIndividualAssessment(...args);
  }

  discloseAssessments(...args: Parameters<typeof this.port.discloseAssessments>) {
    return this.port.discloseAssessments(...args);
  }

  determineComponent(...args: Parameters<typeof this.port.determineComponent>) {
    return this.port.determineComponent(...args);
  }

  recordExternalResult(...args: Parameters<typeof this.port.recordExternalResult>) {
    return this.port.recordExternalResult(...args);
  }

  confirmExternalResult(...args: Parameters<typeof this.port.confirmExternalResult>) {
    return this.port.confirmExternalResult(...args);
  }

  determineExamResult(...args: Parameters<typeof this.port.determineExamResult>) {
    return this.port.determineExamResult(...args);
  }

  confirmResultRecord(...args: Parameters<typeof this.port.confirmResultRecord>) {
    return this.port.confirmResultRecord(...args);
  }

  openResultCorrection(...args: Parameters<typeof this.port.openResultCorrection>) {
    return this.port.openResultCorrection(...args);
  }

  communicateExamResult(...args: Parameters<typeof this.port.communicateExamResult>) {
    return this.port.communicateExamResult(...args);
  }

  setExamResultRetention(...args: Parameters<typeof this.port.setExamResultRetention>) {
    return this.port.setExamResultRetention(...args);
  }
}
