import { Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { map } from 'rxjs';

import { AuthService } from '../auth/auth.service';
import { ExamDayComponent } from '../exam-day/exam-day.component';

/** Route entry for a concrete confirmed examination day. */
@Component({
  imports: [ExamDayComponent],
  template: `
    <app-exam-day
      [roundId]="roundId()"
      [dayId]="dayId()"
      [canCoordinateAttendance]="canCoordinateAttendance()"
      [canWriteOwnAttendance]="canWriteOwnAttendance()"
      [canReportOwnAbsence]="canReportOwnAbsence()"
      [ownMemberId]="auth.session()?.committee_member_id ?? null"
    />
  `,
})
export class ExamDayRouteComponent {
  protected readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  protected readonly roundId = toSignal(
    this.route.paramMap.pipe(map((params) => this.positiveInteger(params.get('roundId')))),
    { initialValue: this.positiveInteger(this.route.snapshot.paramMap.get('roundId')) },
  );
  protected readonly dayId = toSignal(
    this.route.paramMap.pipe(map((params) => this.positiveInteger(params.get('dayId')))),
    { initialValue: this.positiveInteger(this.route.snapshot.paramMap.get('dayId')) },
  );
  protected readonly canCoordinateAttendance = computed(
    () =>
      this.auth.hasCapability('attendance:coordinate') ||
      this.auth.hasCapability('exam-status:write'),
  );
  protected readonly canWriteOwnAttendance = computed(() =>
    this.auth.hasCapability('attendance:write-own'),
  );
  protected readonly canReportOwnAbsence = computed(() =>
    this.auth.hasCapability('absence:write-own'),
  );

  private positiveInteger(parameter: string | null): number | null {
    const value = Number(parameter);
    return Number.isInteger(value) && value > 0 ? value : null;
  }
}
