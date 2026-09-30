import { Injectable, inject } from '@angular/core';

import { ExamDayApplication } from './exam-day.application';

/** UI-facing examination-day operations. */
@Injectable({ providedIn: 'root' })
export class ExamDayFacade {
  private readonly application = inject(ExamDayApplication);

  getConfirmedPlanDay(...args: Parameters<ExamDayApplication['getConfirmedPlanDay']>) {
    return this.application.getConfirmedPlanDay(...args);
  }

  saveCandidateAttendance(...args: Parameters<ExamDayApplication['saveCandidateAttendance']>) {
    return this.application.saveCandidateAttendance(...args);
  }

  saveMemberAttendance(...args: Parameters<ExamDayApplication['saveMemberAttendance']>) {
    return this.application.saveMemberAttendance(...args);
  }

  startExamSlot(...args: Parameters<ExamDayApplication['startExamSlot']>) {
    return this.application.startExamSlot(...args);
  }

  updateExamSlotStatus(...args: Parameters<ExamDayApplication['updateExamSlotStatus']>) {
    return this.application.updateExamSlotStatus(...args);
  }

  closeExamDay(...args: Parameters<ExamDayApplication['closeExamDay']>) {
    return this.application.closeExamDay(...args);
  }

  previewExamDayReopening(...args: Parameters<ExamDayApplication['previewExamDayReopening']>) {
    return this.application.previewExamDayReopening(...args);
  }

  reopenExamDay(...args: Parameters<ExamDayApplication['reopenExamDay']>) {
    return this.application.reopenExamDay(...args);
  }
}
