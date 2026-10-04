import { Component, Input, OnChanges, SimpleChanges, effect, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { TuiButton } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';

import {
  Attendance,
  AttendanceStatus,
  ConfirmedPlanDay,
  ConfirmedPlanDayView,
  ExecutionStatus,
  ExecutionStatusSummary,
  ExamDayReopeningScope,
  ExamDayReopeningScopeKind,
} from './exam-day.models';
import { ExamDayFacade } from './exam-day.facade';
import { AuthService } from '../auth/auth.service';
import { ExamProtocolComponent } from '../exam-protocol/exam-protocol.component';
import { ExamResultComponent } from '../exam-result/exam-result.component';

@Component({
  selector: 'app-exam-day',
  providers: [ExamDayFacade],
  imports: [ExamProtocolComponent, ExamResultComponent, FormsModule, TuiBadge, TuiButton],
  templateUrl: './exam-day.component.html',
  styleUrl: './exam-day.component.css',
})
export class ExamDayComponent implements OnChanges {
  private readonly examDay = inject(ExamDayFacade);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  @Input() roundId: number | null = null;
  @Input() dayId: number | null = null;
  @Input() canCoordinateAttendance = true;
  @Input() canWriteOwnAttendance = true;
  @Input() canReportOwnAbsence = true;
  @Input() ownMemberId: number | null = null;

  protected readonly state = this.examDay.state;
  protected readonly view = this.examDay.view;
  protected readonly actionMessage = this.examDay.actionMessage;
  protected readonly actionError = this.examDay.actionError;
  protected readonly savingKeys = this.examDay.savingKeys;
  protected readonly drafts = new Map<string, AttendanceDraft>();
  protected readonly executionDrafts = new Map<number, ExecutionStatusDraft>();
  protected readonly reopeningImpact = this.examDay.reopeningImpact;
  protected closureType: 'regular' | 'exception' = 'regular';
  protected closureReason = '';
  protected clarificationAttempts = '';
  protected reopeningToken = '';
  protected reopeningOccasion = '';
  protected reopeningSource = '';
  protected reopeningReason = '';
  protected readonly executionSummaryStatuses = [
    { value: 'open', label: 'Offen' },
    { value: 'running', label: 'Läuft' },
    { value: 'completed', label: 'Abgeschlossen' },
    { value: 'cancelled', label: 'Ausgefallen' },
    { value: 'needs_follow_up', label: 'Nachzubereiten' },
  ] as const;

  constructor() {
    effect(() => {
      const view = this.view();
      if (view) this.resetDrafts(view);
    });
    effect(() => {
      this.examDay.contextGeneration();
      this.resetClosureDrafts();
    });
  }
  ngOnChanges(changes: SimpleChanges): void {
    const contextChanged =
      changes['roundId']?.previousValue !== changes['roundId']?.currentValue ||
      changes['dayId']?.previousValue !== changes['dayId']?.currentValue;
    if (contextChanged) {
      this.drafts.clear();
      this.executionDrafts.clear();
      this.resetClosureDrafts();
    }
    this.examDay.bindContext(this.roundId, this.dayId);
  }

  protected load(): void {
    this.examDay.load();
  }

  protected attendanceDraft(key: string, attendance: Attendance | undefined): AttendanceDraft {
    const existing = this.drafts.get(key);
    if (existing) return existing;
    const current = attendance ?? { status: 'open', arrivedAt: null };
    const draft = {
      status: current.status as AttendanceStatus,
      arrivedAt: this.datetimeLocalValue(current.arrivedAt),
    };
    this.drafts.set(key, draft);
    return draft;
  }

  protected candidateAttendanceFor(slot: ConfirmedPlanDay['slots'][number]): Attendance {
    return slot.candidateAttendance ?? { status: 'open', arrivedAt: null };
  }

  protected memberAttendanceFor(assignment: ConfirmedPlanDay['assignments'][number]): Attendance {
    return assignment.attendance ?? { status: 'open', arrivedAt: null };
  }

  protected assignmentsForCurrentRole(): ConfirmedPlanDay['assignments'] {
    const assignments = this.view()?.day.assignments ?? [];
    return !this.canCoordinateAttendance
      ? assignments.filter((assignment) => assignment.member.id === this.ownMemberId)
      : assignments;
  }

  protected saveCandidateAttendance(slotId: number, draft: AttendanceDraft): void {
    if (!this.canCoordinateAttendance || !this.canMutateDayData('candidate_attendance', slotId)) {
      return;
    }
    const dayId = this.view()?.day.id;
    if (dayId === undefined) return;
    this.examDay.saveCandidateAttendance({
      dayId,
      entityId: slotId,
      status: draft.status,
      arrivedAt: this.apiDateTimeValue(draft.arrivedAt),
      dayRevision: this.view()?.day.revision,
    });
  }

  protected saveMemberAttendance(assignmentId: number, draft: AttendanceDraft): void {
    const assignment = this.view()?.day.assignments.find((item) => item.id === assignmentId);
    if (
      !assignment ||
      !this.canEditMemberAttendance(assignment) ||
      !this.canMutateDayData('member_attendance', assignmentId)
    ) {
      return;
    }
    const dayId = this.view()?.day.id;
    if (dayId === undefined) return;
    this.examDay.saveMemberAttendance({
      dayId,
      entityId: assignmentId,
      status: draft.status,
      arrivedAt: this.apiDateTimeValue(draft.arrivedAt),
      dayRevision: this.view()?.day.revision,
    });
  }

  protected startExamSlot(slotId: number): void {
    if (!this.canCoordinateAttendance || !this.canMutateDayData('slot_status', slotId)) return;
    const dayId = this.view()?.day.id;
    if (dayId === undefined) return;
    this.examDay.startExamSlot(dayId, slotId, new Date().toISOString(), this.view()?.day.revision);
  }

  protected reportAbsence(assignmentId: number): void {
    const assignment = this.view()?.day.assignments.find((item) => item.id === assignmentId);
    if (
      !assignment ||
      !this.canReportAbsenceFor(assignment) ||
      !this.canMutateDayData('staffing', assignmentId)
    ) {
      return;
    }
    const dayId = this.view()?.day.id;
    if (dayId === undefined || this.hasSavingAction()) return;
    this.examDay.reportAbsence(dayId, assignmentId, this.view()?.day.revision);
  }

  protected executionStatusDraft(slot: ConfirmedPlanDay['slots'][number]): ExecutionStatusDraft {
    const existing = this.executionDrafts.get(slot.id);
    if (existing) return existing;
    const draft = {
      status: slot.executionStatus,
      reason: slot.statusReason ?? '',
      actualStartedAt: this.datetimeLocalValue(slot.actualStartedAt),
      actualCompletedAt: this.datetimeLocalValue(slot.actualCompletedAt),
    };
    this.executionDrafts.set(slot.id, draft);
    return draft;
  }

  protected executionStatusOptions(
    status: ExecutionStatus,
    slotId: number,
  ): Array<ExecutionStatusOption> {
    if (this.isReopenedScope('slot_status', slotId)) {
      return this.executionSummaryStatuses.map((option) => ({ ...option }));
    }
    if (status === 'open') {
      return [
        { value: 'open', label: 'Offen' },
        { value: 'cancelled', label: 'Ausgefallen' },
      ];
    }
    if (status === 'running') {
      return [
        { value: 'running', label: 'Läuft' },
        { value: 'completed', label: 'Abgeschlossen' },
        { value: 'needs_follow_up', label: 'Nachzubereiten' },
      ];
    }
    if (status === 'needs_follow_up') {
      return [
        { value: 'needs_follow_up', label: 'Nachzubereiten' },
        { value: 'completed', label: 'Abgeschlossen' },
      ];
    }
    return [{ value: status, label: this.executionStatusLabel(status) }];
  }

  protected requiresExecutionReason(status: ExecutionStatus): boolean {
    return status === 'cancelled' || status === 'needs_follow_up';
  }

  protected isTerminalExecutionStatus(status: ExecutionStatus): boolean {
    return status === 'completed' || status === 'cancelled';
  }

  protected saveExecutionStatus(slotId: number, draft: ExecutionStatusDraft): void {
    if (!this.canCoordinateAttendance || !this.canMutateDayData('slot_status', slotId)) return;
    const dayId = this.view()?.day.id;
    if (dayId === undefined) return;
    if (this.requiresExecutionReason(draft.status) && !draft.reason.trim()) {
      this.examDay.showValidationError(
        'Für einen Ausfall oder eine Nachbereitung ist eine Begründung erforderlich.',
      );
      return;
    }
    this.examDay.updateExamSlotStatus({
      dayId,
      slotId,
      status: draft.status,
      reason: draft.reason.trim(),
      dayRevision: this.view()?.day.revision,
      actualStartedAt: this.isReopenedScope('slot_status', slotId)
        ? this.apiDateTimeValue(draft.actualStartedAt)
        : undefined,
      actualCompletedAt: this.isReopenedScope('slot_status', slotId)
        ? this.apiDateTimeValue(draft.actualCompletedAt)
        : undefined,
    });
  }

  protected closeDay(): void {
    const day = this.view()?.day;
    if (!day || !day.closure.permissions.close || !this.can('exam-day-closure:close')) return;
    if (
      this.closureType === 'exception' &&
      (!this.closureReason.trim() || !this.clarificationAttempts.trim())
    ) {
      this.examDay.showValidationError('Grund und bisherige Klärungsversuche sind erforderlich.');
      return;
    }
    this.examDay.closeExamDay({
      dayId: day.id,
      revision: day.revision,
      closureType: this.closureType,
      reason: this.closureReason,
      clarificationAttempts: this.clarificationAttempts,
    }, 'Prüfungstag formal abgeschlossen.');
  }

  protected previewReopening(): void {
    const day = this.view()?.day;
    const scope = this.selectedReopeningScope();
    if (
      !day ||
      !scope ||
      !day.closure.permissions.reopen ||
      !this.can('exam-day-closure:preview-reopening')
    ) {
      return;
    }
    this.examDay.previewReopening(day.id, [scope]);
  }

  protected reopenDay(): void {
    const day = this.view()?.day;
    const scope = this.selectedReopeningScope();
    if (!day || !scope || !this.can('exam-day-closure:reopen')) return;
    if (
      !this.reopeningImpact() ||
      !this.reopeningOccasion.trim() ||
      !this.reopeningSource.trim() ||
      !this.reopeningReason.trim()
    ) {
      this.examDay.showValidationError(
        'Auswirkungsprüfung, Anlass, Quelle und fachliche Begründung sind erforderlich.',
      );
      return;
    }
    this.examDay.reopenExamDay({
      dayId: day.id,
      revision: day.revision,
      occasion: this.reopeningOccasion,
      source: this.reopeningSource,
      reason: this.reopeningReason,
      scope: [scope],
    }, 'Prüfungstag zielgerichtet wieder geöffnet.');
  }

  protected canMutateDayData(kind: string, entityId: number): boolean {
    const closure = this.view()?.day.closure;
    if (!closure || closure.status === 'open') return true;
    if (closure.status !== 'reopening') return false;
    const scope = closure.activeReopening?.expandedScope;
    return Array.isArray(scope) && scope.includes(`${kind}:${entityId}`);
  }

  protected isReopenedScope(kind: string, entityId: number): boolean {
    return this.view()?.day.closure.status === 'reopening' && this.canMutateDayData(kind, entityId);
  }

  protected can(capability: string): boolean {
    return this.auth.hasCapability(capability);
  }

  protected closureStatusLabel(status: string): string {
    return (
      {
        open: 'Offen',
        closed: 'Geschlossen',
        closed_exception: 'Mit Ausnahme geschlossen',
        reopening: 'Wiederöffnung läuft',
        historical: 'Historischer Status ohne lzug-Abschlussnachweis',
      }[status] ?? status
    );
  }

  protected reopeningOptions(): Array<{ value: string; label: string }> {
    const day = this.view()?.day;
    if (!day) return [];
    const options = day.slots.flatMap((slot) => [
      { value: `slot_status:${slot.id}`, label: `Slot ${slot.id}: Durchführung` },
      { value: `candidate_attendance:${slot.id}`, label: `Slot ${slot.id}: Anwesenheit` },
    ]);
    options.push(
      ...day.assignments.flatMap((assignment) => [
        {
          value: `member_attendance:${assignment.id}`,
          label: `Besetzung ${assignment.id}: Anwesenheit`,
        },
        { value: `staffing:${assignment.id}`, label: `Besetzung ${assignment.id}: Zuordnung` },
      ]),
    );
    for (const reference of day.closure.evaluation.protocolReferences) {
      const id = reference.protocolId;
      if (typeof id === 'number') {
        options.push({ value: `exam_protocol:${id}`, label: `Prüfungsprotokoll ${id}` });
      }
    }
    for (const reference of day.closure.evaluation.resultReferences) {
      const id = reference.resultId;
      if (typeof id === 'number') {
        options.push({ value: `exam_result:${id}`, label: `Bewertung und Ergebnis ${id}` });
      }
    }
    return options;
  }

  protected statusLabel(status: string): string {
    return (
      {
        open: 'Offen',
        present: 'Anwesend',
        late: 'Verspätet',
        absent: 'Abwesend',
      }[status] ?? 'Unbekannter Status'
    );
  }

  protected statusAppearance(status: string): 'neutral' | 'positive' | 'warning' | 'negative' {
    if (status === 'present') return 'positive';
    if (status === 'late') return 'warning';
    if (status === 'absent') return 'negative';
    return 'neutral';
  }

  protected executionStatusLabel(status: string): string {
    return (
      {
        open: 'Offen',
        running: 'Läuft',
        completed: 'Abgeschlossen',
        cancelled: 'Ausgefallen',
        needs_follow_up: 'Nachzubereiten',
      }[status] ?? 'Unbekannter Durchführungsstatus'
    );
  }

  protected executionStatusAppearance(
    status: string,
  ): 'neutral' | 'positive' | 'warning' | 'negative' {
    if (status === 'running' || status === 'completed') return 'positive';
    if (status === 'needs_follow_up') return 'warning';
    if (status === 'cancelled') return 'negative';
    return 'neutral';
  }

  protected executionStatusCount(summary: ExecutionStatusSummary, status: string): number {
    return summary[status as keyof ExecutionStatusSummary] ?? 0;
  }

  protected arrivalLabel(value: string | null): string {
    if (!value) return 'Keine Ankunftszeit erfasst';
    return new Intl.DateTimeFormat('de-DE', { dateStyle: 'short', timeStyle: 'short' }).format(
      new Date(value),
    );
  }

  protected isSaving(key: string): boolean {
    return this.savingKeys().has(key);
  }

  protected hasSavingAction(): boolean {
    return this.savingKeys().size > 0;
  }

  protected canEditMemberAttendance(assignment: ConfirmedPlanDay['assignments'][number]): boolean {
    return (
      this.canMutateDayData('member_attendance', assignment.id) &&
      (this.canCoordinateAttendance ||
        (this.canWriteOwnAttendance && assignment.member.id === this.ownMemberId))
    );
  }

  protected canReportAbsenceFor(assignment: ConfirmedPlanDay['assignments'][number]): boolean {
    return (
      this.canReportOwnAbsence &&
      this.canMutateDayData('staffing', assignment.id) &&
      (this.canCoordinateAttendance || assignment.member.id === this.ownMemberId)
    );
  }

  private selectedReopeningScope(): ExamDayReopeningScope | null {
    const [kind, rawId] = this.reopeningToken.split(':');
    const entityId = Number(rawId);
    if (!kind || !Number.isInteger(entityId) || entityId < 1) return null;
    return { kind: kind as ExamDayReopeningScopeKind, entityId };
  }

  private resetClosureDrafts(): void {
    this.closureType = 'regular';
    this.closureReason = '';
    this.clarificationAttempts = '';
    this.reopeningToken = '';
    this.reopeningOccasion = '';
    this.reopeningSource = '';
    this.reopeningReason = '';
  }

  private resetDrafts(view: ConfirmedPlanDayView): void {
    this.drafts.clear();
    this.executionDrafts.clear();
    for (const slot of view.day.slots) {
      this.attendanceDraft(`candidate-${slot.id}`, this.candidateAttendanceFor(slot));
      this.executionStatusDraft(slot);
    }
    for (const assignment of view.day.assignments) {
      this.attendanceDraft(`member-${assignment.id}`, this.memberAttendanceFor(assignment));
    }
  }

  private datetimeLocalValue(value: string | null): string {
    return value ? value.replace(/([+-]\d{2}:?\d{2}|Z)$/, '').slice(0, 16) : '';
  }

  private apiDateTimeValue(value: string): string | null {
    return value ? new Date(value).toISOString() : null;
  }

  protected backHref(): string {
    const roundId = this.view()?.plan.id ?? this.roundId;
    return roundId === null ? '/confirmed-plans' : `/confirmed-plans/${roundId}`;
  }

  protected goBack(event: MouseEvent): void {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    void this.router.navigateByUrl(this.backHref());
  }

  protected dateLabel(date: string): string {
    return new Intl.DateTimeFormat('de-DE', { dateStyle: 'full' }).format(
      new Date(`${date}T12:00:00`),
    );
  }

  protected timeLabel(value: string): string {
    return value.match(/(\d{2}:\d{2})/)?.[1] ?? 'Uhrzeit nicht angegeben';
  }

  protected examLabel(slotType: string): string {
    return { regular: 'Reguläre Prüfung', mep: 'MEP-Prüfung' }[slotType] ?? 'Prüfung';
  }

  protected roleLabel(role: string): string {
    return { examiner: 'Prüfer/in', fallback: 'Ersatzprüfer/in' }[role] ?? 'Prüferbesetzung';
  }

  protected dayPartLabel(dayPart: string): string {
    return (
      { morning: 'vormittags', afternoon: 'nachmittags', full_day: 'ganztägig' }[dayPart] ??
      'Zeitfenster nicht angegeben'
    );
  }

  protected representingSideLabel(side: string): string {
    return (
      { employer: 'Arbeitgeber', employee: 'Arbeitnehmer', school: 'Schule' }[side] ??
      'Vertreterseite nicht angegeben'
    );
  }

  protected fallbackStatusLabel(
    status: ConfirmedPlanDay['assignments'][number]['fallbackStatus'],
  ): string {
    if (status === 'confirmed') return 'Bestätigt';
    if (status === 'proposed') return 'Vorgesehen';
    return 'Nicht zutreffend';
  }

  protected refreshAfterProtocolChange(change: {
    roundId: number;
    dayId: number;
    revision: number;
  }): void {
    if (change.roundId !== this.roundId) return;
    this.examDay.refreshAfterEmbeddedMutation(change.dayId, change.revision);
  }

  protected refreshAfterResultChange(dayRevisions: Record<string, number>): void {
    const dayId = this.view()?.day.id;
    if (dayId === undefined) return;
    const revision = dayRevisions[String(dayId)];
    if (revision !== undefined && revision > (this.view()?.day.revision ?? 0)) {
      this.examDay.refreshAfterEmbeddedMutation(dayId, revision);
    }
  }
}

export type AttendanceDraft = { status: AttendanceStatus; arrivedAt: string };
export type ExecutionStatusDraft = {
  status: ExecutionStatus;
  reason: string;
  actualStartedAt: string;
  actualCompletedAt: string;
};
export type ExecutionStatusOption = { value: ExecutionStatus; label: string };
