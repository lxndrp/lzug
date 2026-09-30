import { Injectable, inject } from '@angular/core';

import { ExamResultApplication } from './exam-result.application';

/** UI-facing operations for the exam assessment/result feature. */
@Injectable({ providedIn: 'root' })
export class ExamResultFacade {
  private readonly application = inject(ExamResultApplication);

  get(...args: Parameters<ExamResultApplication['get']>) {
    return this.application.get(...args);
  }

  saveIndividualAssessment(...args: Parameters<ExamResultApplication['saveIndividualAssessment']>) {
    return this.application.saveIndividualAssessment(...args);
  }

  withdrawIndividualAssessment(
    ...args: Parameters<ExamResultApplication['withdrawIndividualAssessment']>
  ) {
    return this.application.withdrawIndividualAssessment(...args);
  }

  discloseAssessments(...args: Parameters<ExamResultApplication['discloseAssessments']>) {
    return this.application.discloseAssessments(...args);
  }

  determineComponent(...args: Parameters<ExamResultApplication['determineComponent']>) {
    return this.application.determineComponent(...args);
  }

  recordExternalResult(...args: Parameters<ExamResultApplication['recordExternalResult']>) {
    return this.application.recordExternalResult(...args);
  }

  confirmExternalResult(...args: Parameters<ExamResultApplication['confirmExternalResult']>) {
    return this.application.confirmExternalResult(...args);
  }

  determineExamResult(...args: Parameters<ExamResultApplication['determineExamResult']>) {
    return this.application.determineExamResult(...args);
  }

  confirmResultRecord(...args: Parameters<ExamResultApplication['confirmResultRecord']>) {
    return this.application.confirmResultRecord(...args);
  }

  openResultCorrection(...args: Parameters<ExamResultApplication['openResultCorrection']>) {
    return this.application.openResultCorrection(...args);
  }

  communicateExamResult(...args: Parameters<ExamResultApplication['communicateExamResult']>) {
    return this.application.communicateExamResult(...args);
  }

  setExamResultRetention(...args: Parameters<ExamResultApplication['setExamResultRetention']>) {
    return this.application.setExamResultRetention(...args);
  }
}
