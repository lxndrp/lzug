import { Injectable, inject } from '@angular/core';

import { EXAM_DAY_PORT } from './exam-day.port';

/** Application operations for the examination-day feature. */
@Injectable({ providedIn: 'root' })
export class ExamDayApplication {
  private readonly port = inject(EXAM_DAY_PORT);

  getConfirmedPlanDay(dayId: number) {
    return this.port.getConfirmedPlanDay(dayId);
  }

  saveCandidateAttendance(...args: Parameters<typeof this.port.saveCandidateAttendance>) {
    return this.port.saveCandidateAttendance(...args);
  }

  saveMemberAttendance(...args: Parameters<typeof this.port.saveMemberAttendance>) {
    return this.port.saveMemberAttendance(...args);
  }

  startExamSlot(...args: Parameters<typeof this.port.startExamSlot>) {
    return this.port.startExamSlot(...args);
  }

  updateExamSlotStatus(...args: Parameters<typeof this.port.updateExamSlotStatus>) {
    return this.port.updateExamSlotStatus(...args);
  }

  closeExamDay(...args: Parameters<typeof this.port.closeExamDay>) {
    return this.port.closeExamDay(...args);
  }

  previewExamDayReopening(...args: Parameters<typeof this.port.previewExamDayReopening>) {
    return this.port.previewExamDayReopening(...args);
  }

  reopenExamDay(...args: Parameters<typeof this.port.reopenExamDay>) {
    return this.port.reopenExamDay(...args);
  }
}
